"""Critérios de alerta (§53): o usuário escolhe QUAIS mudanças quer receber.

Antes, monitorar era tudo-ou-nada. Aqui se garante o contrário: cada critério
só alerta quando há fato novo DELE, e critério desligado não emite nada.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.db.session import rls_session
from src.models.alerta import Alerta
from src.models.monitoramento import Monitoramento, MonitoramentoBusca
from src.models.proposta import Proposta
from src.models.usuario import Usuario
from src.services import criterios_alerta, detect_changes
from src.services import monitoramentos as mon_service
from src.services import oportunidades as oport_service


def _proposta(**campos) -> SimpleNamespace:
    base = {
        "situacao": "Em análise",
        "movimentacao": None,
        "prazos": None,
        "pendencias": None,
        "execucao": None,
    }
    return SimpleNamespace(**{**base, **campos})


# ── registro ────────────────────────────────────────────────────────────────
def test_catalogo_separa_escopos() -> None:
    proposta = criterios_alerta.chaves(criterios_alerta.ESCOPO_PROPOSTA)
    territorio = criterios_alerta.chaves(criterios_alerta.ESCOPO_TERRITORIO)
    assert {"parecer", "empenho", "pagamento", "publicacao", "vencimento"} <= proposta
    assert territorio == {"nova_proposta", "oportunidade"}
    assert not proposta & territorio


def test_efetivos_distingue_ausencia_de_lista_vazia() -> None:
    # NULL = padrões (monitoramento criado antes da escolha existir)
    assert criterios_alerta.efetivos(None, criterios_alerta.ESCOPO_PROPOSTA) == (
        criterios_alerta.padroes(criterios_alerta.ESCOPO_PROPOSTA)
    )
    # lista vazia é escolha legítima: silêncio, não "tudo de novo"
    assert criterios_alerta.efetivos([], criterios_alerta.ESCOPO_PROPOSTA) == set()
    assert criterios_alerta.efetivos(["empenho"], criterios_alerta.ESCOPO_PROPOSTA) == {"empenho"}


def test_validar_recusa_chave_inventada_e_de_outro_escopo() -> None:
    with pytest.raises(ValueError):
        criterios_alerta.validar(["xpto"], criterios_alerta.ESCOPO_PROPOSTA)
    with pytest.raises(ValueError):
        criterios_alerta.validar(["nova_proposta"], criterios_alerta.ESCOPO_PROPOSTA)


# ── detecção por critério (pura) ────────────────────────────────────────────
def test_snapshot_le_execucao_pareceres_e_empenhos() -> None:
    p = _proposta(
        execucao={
            "valor_empenhado": "1000",
            "valor_pago": "250,00",
            "situacao_publicacao": "Publicado",
            "data_fim_vigencia": "2026-12-31",
        }
    )
    empenho = SimpleNamespace(
        valor_empenhado=Decimal("600"),
        valor_anulado=Decimal("100"),
        valor_pago=Decimal("250"),
    )
    parecer = SimpleNamespace(
        id_externo="9", situacao="Aprovar", situacao_analise="Concluída", hash_conteudo="h"
    )
    snap = detect_changes.snapshot(
        p, pareceres=[parecer], empenhos=[empenho], hoje=date(2026, 12, 1)
    )
    assert snap["valor_empenhado"] == "1000"
    assert snap["publicacao_situacao"] == "Publicado"
    assert snap["empenhos_empenhado"] == "500"  # líquido da anulação
    assert snap["pareceres_total"] == 1
    assert snap["fim_vigencia"] == "2026-12-31"
    assert snap["dias_para_vencer"] == 30
    assert snap["vencimento_proximo"] is True


def test_avaliar_emite_um_alerta_por_criterio_ligado() -> None:
    antes = detect_changes.snapshot(
        _proposta(execucao={"valor_empenhado": "100", "valor_pago": "0"}),
        hoje=date(2026, 1, 1),
    )
    depois = detect_changes.snapshot(
        _proposta(
            situacao="Aprovada",
            execucao={"valor_empenhado": "900", "valor_pago": "300"},
        ),
        hoje=date(2026, 1, 1),
    )
    todos = {
        m.criterio
        for m in detect_changes.avaliar(antes, depois, {"situacao", "empenho", "pagamento"})
    }
    assert todos == {"situacao", "empenho", "pagamento"}
    # só empenho ligado → só um alerta, e é o do empenho
    (so_empenho,) = detect_changes.avaliar(antes, depois, {"empenho"})
    assert so_empenho.criterio == "empenho"
    assert "empenhado" in so_empenho.payload["resumo"]


def test_avaliar_nao_alerta_sem_linha_de_base() -> None:
    """Primeira varredura só fotografa — senão a proposta inteira 'mudou'."""
    atual = detect_changes.snapshot(_proposta(), hoje=date(2026, 1, 1))
    assert detect_changes.avaliar(None, atual, {"situacao", "empenho"}) == []


def test_parecer_alerta_no_novo_e_na_mudanca_de_veredito() -> None:
    p = _proposta()
    parecer = SimpleNamespace(
        id_externo="1", situacao="Em elaboração", situacao_analise=None, hash_conteudo=None
    )
    vazio = detect_changes.snapshot(p, pareceres=[], hoje=date(2026, 1, 1))
    com_parecer = detect_changes.snapshot(p, pareceres=[parecer], hoje=date(2026, 1, 1))
    (novo,) = detect_changes.avaliar(vazio, com_parecer, {"parecer"})
    assert novo.criterio == "parecer"

    aprovado = SimpleNamespace(
        id_externo="1", situacao="Aprovar", situacao_analise=None, hash_conteudo=None
    )
    virou = detect_changes.snapshot(p, pareceres=[aprovado], hoje=date(2026, 1, 1))
    (mudou,) = detect_changes.avaliar(com_parecer, virou, {"parecer"})
    assert mudou.criterio == "parecer"


def test_vencimento_avisa_ao_entrar_na_janela_e_nao_repete_por_dia() -> None:
    p = _proposta(execucao={"data_fim_vigencia": "2026-03-01"})
    longe = detect_changes.snapshot(p, hoje=date(2026, 1, 1))
    dentro = detect_changes.snapshot(p, hoje=date(2026, 2, 10))
    mais_perto = detect_changes.snapshot(p, hoje=date(2026, 2, 20))

    assert detect_changes.avaliar(longe, longe, {"vencimento"}) == []
    (aviso,) = detect_changes.avaliar(longe, dentro, {"vencimento"})
    assert aviso.criterio == "vencimento"
    assert aviso.payload["dias_para_vencer"] == 19
    # dia seguinte: continua na janela, mas não há fato novo — nada de alerta
    assert detect_changes.avaliar(dentro, mais_perto, {"vencimento"}) == []


def test_vencimento_avisa_convenio_ja_vencendo_no_primeiro_olhar() -> None:
    """Vencimento é ESTADO: quem monitora hoje um convênio a vencer em 5 dias
    precisa saber hoje, não no próximo movimento da fonte."""
    atual = detect_changes.snapshot(
        _proposta(execucao={"data_fim_vigencia": "2026-01-06"}), hoje=date(2026, 1, 1)
    )
    (aviso,) = detect_changes.avaliar(None, atual, {"vencimento"})
    assert aviso.criterio == "vencimento"
    assert detect_changes.avaliar(None, atual, {"situacao"}) == []


def test_podar_descarta_campo_de_criterio_desligado() -> None:
    snap = detect_changes.snapshot(_proposta(), hoje=date(2026, 1, 1))
    podado = detect_changes.podar(snap, {"situacao"})
    assert "situacao" in podado
    assert "pareceres_total" not in podado and "valor_empenhado" not in podado
    # sem o campo, ligar o critério depois recomeça a linha de base (nada emite)
    assert detect_changes.avaliar(podado, snap, {"parecer"}) == []


# ── varredura ponta a ponta ─────────────────────────────────────────────────
async def _usuario(s, uid) -> Usuario:
    return (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()


async def test_varredura_alerta_so_os_criterios_escolhidos(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("crit@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta(
        "transferegov_ff",
        "P-CRIT",
        "3550308",
        situacao="Em análise",
        execucao=json.dumps({"valor_empenhado": "100"}),  # jsonb no INSERT cru
    )
    async with rls_session(u) as s:
        await mon_service.criar(s, u, pid, ["painel"], criterios=["empenho"])
        # 1ª varredura: só fotografa
        assert await oport_service.varredura(s, await _usuario(s, u)) == 0
        mon = (await s.execute(select(Monitoramento))).scalar_one()
        assert mon.snapshot is not None

    # a fonte mexeu na situação (critério DESLIGADO) e no empenho (ligado)
    async with rls_session(u) as s:
        proposta = (await s.execute(select(Proposta).where(Proposta.id == pid))).scalar_one()
        proposta.situacao = "Aprovada"
        proposta.execucao = {"valor_empenhado": "900"}
        await s.flush()
        await oport_service.varredura(s, await _usuario(s, u))
        alertas = (await s.execute(select(Alerta))).scalars().all()
        assert [a.tipo for a in alertas] == ["empenho"]
        assert alertas[0].payload["numero_proposta"] is None
        assert alertas[0].payload["municipio_ibge"] == "3550308"
        mon = (await s.execute(select(Monitoramento))).scalar_one()
        assert mon.ultimo_alerta_em is not None

    # sem fato novo, a varredura seguinte não repete o alerta
    async with rls_session(u) as s:
        await oport_service.varredura(s, await _usuario(s, u))
        assert len((await s.execute(select(Alerta))).scalars().all()) == 1


async def test_busca_sem_nova_proposta_nao_alerta(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("silencio@x.com")
    await seed_municipio(u, "3550308")
    async with rls_session(u) as s:
        await mon_service.criar_busca(
            s,
            u,
            municipio_ibge="3550308",
            area=None,
            fonte=None,
            canais=["painel"],
            criterios=["oportunidade"],  # quer oportunidade, não proposta nova
        )
    await seed_proposta("transferegov_ff", "NOVA-1", "3550308")
    async with rls_session(u) as s:
        await oport_service.varredura(s, await _usuario(s, u))
        tipos = [a.tipo for a in (await s.execute(select(Alerta))).scalars().all()]
        assert "nova_proposta" not in tipos
        busca = (await s.execute(select(MonitoramentoBusca))).scalar_one()
        assert busca.criterios == ["oportunidade"]


async def test_oportunidade_desligada_na_busca_nao_alerta(
    seed_user, seed_municipio, seed_repasse
) -> None:
    u = await seed_user("semoport@x.com")
    await seed_municipio(u, "3550308")
    await seed_repasse("fns", "R1", "3550308", valor="500000")
    async with rls_session(u) as s:
        await mon_service.criar_busca(
            s,
            u,
            municipio_ibge="3550308",
            area=None,
            fonte=None,
            canais=["painel"],
            criterios=["nova_proposta"],
        )
        assert await oport_service.varredura(s, await _usuario(s, u)) == 0


async def test_monitoramento_criado_antes_da_feature_mantem_tudo(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """`criterios` NULL = padrões: quem já monitorava não perde alerta."""
    u = await seed_user("legado@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-LEG", "3550308", situacao="Em análise")
    async with rls_session(u) as s:
        mon = await mon_service.criar(s, u, pid, ["painel"])
        assert mon.criterios is None
        await oport_service.varredura(s, await _usuario(s, u))
    async with rls_session(u) as s:
        proposta = (await s.execute(select(Proposta).where(Proposta.id == pid))).scalar_one()
        proposta.situacao = "Aprovada"
        proposta.pendencias = [{"descricao": "Enviar plano", "prazo": "2026-09-01"}]
        await s.flush()
        await oport_service.varredura(s, await _usuario(s, u))
        tipos = {a.tipo for a in (await s.execute(select(Alerta))).scalars().all()}
        assert tipos == {"situacao", "pendencia"}


async def test_reconfigurar_monitoramento_troca_os_criterios(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Não há PATCH: o POST é upsert e é assim que o multi-select edita."""
    u = await seed_user("recfg@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-RE", "3550308")
    async with rls_session(u) as s:
        await mon_service.criar(s, u, pid, ["painel"], criterios=["empenho"])
        mon = await mon_service.criar(s, u, pid, ["painel", "email"], criterios=["parecer"])
        assert mon.criterios == ["parecer"]
        assert set(mon.canais or []) == {"painel", "email"}
        assert len((await s.execute(select(Monitoramento))).scalars().all()) == 1


async def test_alerta_de_mudanca_vira_linha_legivel_no_despacho() -> None:
    alerta = Alerta(
        tipo="vencimento",
        payload={
            "resumo": "Convênio vence em 10 dia(s) (2026-09-01)",
            "titulo": "Reforma da UBS",
            "municipio_nome": "São Paulo",
        },
    )
    linha = oport_service._linha(alerta)
    assert "Vencimento do convênio" in linha and "Reforma da UBS" in linha


def test_janela_de_vencimento_e_a_do_registro() -> None:
    fim = date.today() + timedelta(days=criterios_alerta.JANELA_VENCIMENTO_DIAS)
    snap = detect_changes.snapshot(
        _proposta(execucao={"data_fim_vigencia": fim.isoformat()}),
        hoje=datetime.now(UTC).date(),
    )
    assert snap["vencimento_proximo"] is True
