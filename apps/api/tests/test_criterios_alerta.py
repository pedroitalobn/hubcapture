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
from sqlalchemy import select, text

from src.db.session import rls_session
from src.models.alerta import Alerta
from src.models.monitoramento import Monitoramento, MonitoramentoBusca
from src.models.proposta import Proposta
from src.models.usuario import Usuario
from src.services import criterios_alerta, detect_changes
from src.services import favoritos as fav_service
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
    # "oportunidade" foi RETIRADO do catálogo (§56) e não volta ao multi-select
    assert territorio == {"nova_proposta"}
    assert "oportunidade" not in criterios_alerta.chaves()
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


def test_parecer_novo_e_parecer_atualizado_sao_criterios_distintos() -> None:
    """Novo parecer ≠ veredito alterado: o gestor escolhe cada um."""
    p = _proposta()
    parecer = SimpleNamespace(
        id_externo="1", situacao="Em elaboração", situacao_analise=None, hash_conteudo=None
    )
    vazio = detect_changes.snapshot(p, pareceres=[], hoje=date(2026, 1, 1))
    com_parecer = detect_changes.snapshot(p, pareceres=[parecer], hoje=date(2026, 1, 1))

    (novo,) = detect_changes.avaliar(vazio, com_parecer, {"parecer_novo", "parecer"})
    assert novo.criterio == "parecer_novo"  # entrou um parecer: não é "atualizado"
    assert novo.payload["pareceres_novos"] == ["1"]

    aprovado = SimpleNamespace(
        id_externo="1", situacao="Aprovar", situacao_analise=None, hash_conteudo=None
    )
    virou = detect_changes.snapshot(p, pareceres=[aprovado], hoje=date(2026, 1, 1))
    (mudou,) = detect_changes.avaliar(com_parecer, virou, {"parecer_novo", "parecer"})
    assert mudou.criterio == "parecer"  # o MESMO parecer mudou de veredito
    assert "Em elaboração → Aprovar" in mudou.payload["resumo"]

    # parecer que some da fonte não é "novo parecer"
    assert detect_changes.avaliar(virou, vazio, {"parecer_novo"}) == []


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
    assert "emendas_total" not in podado and "dias_para_vencer" not in podado
    # sem o campo, ligar o critério depois recomeça a linha de base (nada emite)
    assert detect_changes.avaliar(podado, snap, {"parecer", "parecer_novo"}) == []


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
            criterios=[],  # vigia o território, mas não quer aviso de proposta nova
        )
    await seed_proposta("transferegov_ff", "NOVA-1", "3550308")
    async with rls_session(u) as s:
        await oport_service.varredura(s, await _usuario(s, u))
        tipos = [a.tipo for a in (await s.execute(select(Alerta))).scalars().all()]
        assert "nova_proposta" not in tipos
        busca = (await s.execute(select(MonitoramentoBusca))).scalar_one()
        assert busca.criterios == []


async def test_repasse_sem_proposta_nao_gera_mais_alerta(
    seed_user, seed_municipio, seed_repasse
) -> None:
    """O alerta 'oportunidade' foi retirado: repasse sem proposta é o normal do
    repasse constitucional, e o aviso disparava sempre (§56)."""
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


# ── critérios novos: empenho pago, emenda aplicada, proposta publicada ──────
def test_empenho_e_empenho_pago_sao_avisos_diferentes() -> None:
    """Emitir empenho ≠ pagar empenho: quem só quer saber do dinheiro que saiu
    marca `empenho_pago` e não recebe o resto."""
    p = _proposta()
    emitido = SimpleNamespace(
        valor_empenhado=Decimal("1000"),
        valor_anulado=None,
        valor_liquidado=None,
        valor_pago=None,
    )
    pago = SimpleNamespace(
        valor_empenhado=Decimal("1000"),
        valor_anulado=None,
        valor_liquidado=Decimal("400"),
        valor_pago=Decimal("400"),
    )
    antes = detect_changes.snapshot(p, empenhos=[emitido], hoje=date(2026, 1, 1))
    depois = detect_changes.snapshot(p, empenhos=[pago], hoje=date(2026, 1, 1))

    (so_pago,) = detect_changes.avaliar(antes, depois, {"empenho", "empenho_pago"})
    assert so_pago.criterio == "empenho_pago"  # o empenhado não mudou

    novo_empenho = detect_changes.snapshot(p, empenhos=[emitido, emitido], hoje=date(2026, 1, 1))
    (so_empenho,) = detect_changes.avaliar(antes, novo_empenho, {"empenho", "empenho_pago"})
    assert so_empenho.criterio == "empenho"


def test_emenda_aplicada_alerta_com_o_autor() -> None:
    p = _proposta()
    emenda = SimpleNamespace(
        id_externo="E1",
        hash_conteudo=None,
        parlamentar="Dep. Fulano",
        valor=Decimal("500000"),
        valor_empenhado=Decimal("0"),
        valor_pago=Decimal("0"),
    )
    sem = detect_changes.snapshot(p, emendas=[], hoje=date(2026, 1, 1))
    com = detect_changes.snapshot(p, emendas=[emenda], hoje=date(2026, 1, 1))
    (aplicada,) = detect_changes.avaliar(sem, com, {"emenda"})
    assert aplicada.criterio == "emenda"
    assert "Dep. Fulano" in aplicada.payload["resumo"]
    assert aplicada.payload["emendas_novas"] == ["E1"]

    # empenho da MESMA emenda: continua sendo alerta de emenda, sem "aplicada"
    empenhada = SimpleNamespace(
        id_externo="E1",
        hash_conteudo=None,
        parlamentar="Dep. Fulano",
        valor=Decimal("500000"),
        valor_empenhado=Decimal("500000"),
        valor_pago=Decimal("0"),
    )
    depois = detect_changes.snapshot(p, emendas=[empenhada], hoje=date(2026, 1, 1))
    (mudou,) = detect_changes.avaliar(com, depois, {"emenda"})
    assert mudou.payload["emendas_novas"] == []
    assert "Valores da emenda" in mudou.payload["resumo"]


def test_proposta_publicada_e_estado_nao_so_texto() -> None:
    p = _proposta()
    antes = detect_changes.snapshot(p, hoje=date(2026, 1, 1)) | {
        "publicada": False,
        "publicacao_situacao": "Não publicado",
        "publicacao_valor": None,
    }
    publicada = detect_changes.snapshot(
        _proposta(execucao={"situacao_publicacao": "Publicado em 12/03/2026"}),
        hoje=date(2026, 1, 1),
    )
    assert publicada["publicada"] is True
    (aviso,) = detect_changes.avaliar(antes, publicada, {"publicacao"})
    assert aviso.criterio == "publicacao"
    assert aviso.payload["resumo"] == "Proposta publicada na fonte"

    # "Não publicado" não conta como publicada (senão todo registro nasceria publicado)
    assert (
        detect_changes.snapshot(
            _proposta(execucao={"situacao_publicacao": "Não publicado"}), hoje=date(2026, 1, 1)
        )["publicada"]
        is False
    )


def test_alerta_de_publicacao_nao_anuncia_publicacao_que_nao_houve() -> None:
    """Ponto 11: o alerta saía rotulado "Proposta publicada" com o texto
    "publicação atualizado(s)" para uma proposta NÃO publicada. O critério
    cobre três fatos; cada um agora tem a sua frase."""
    p = _proposta()
    base = detect_changes.snapshot(p, hoje=date(2026, 1, 1)) | {
        "publicada": False,
        "publicacao_situacao": None,
        "publicacao_valor": None,
    }
    # a fonte passou a informar a situação — e ela é NEGATIVA
    depois = detect_changes.snapshot(
        _proposta(execucao={"situacao_publicacao": "Não Publicado"}), hoje=date(2026, 1, 1)
    )
    assert depois["publicada"] is False
    (aviso,) = detect_changes.avaliar(base, depois, {"publicacao"})
    resumo = aviso.payload["resumo"]
    assert "Não Publicado" in resumo
    assert "Proposta publicada" not in resumo
    # e a pílula do alerta não afirma publicação
    assert criterios_alerta.rotulo("publicacao") == "Publicação"


def test_publicacao_le_tri_estado_e_nao_chuta() -> None:
    """Ponto 09: "sim" (o valor do campo VIZINHO, capturado por engano) não
    pode virar "publicado" — a proposta aparecia no Hub como publicada e no
    TransfereGov como Não Publicado."""
    from src.services import publicacao

    assert publicacao.estado("sim") == publicacao.SEM_INFORMACAO
    assert publicacao.estado("Publicado") == publicacao.PUBLICADO
    assert publicacao.estado("Não Publicado") == publicacao.NAO_PUBLICADO
    assert publicacao.estado("Publicação Pendente") == publicacao.NAO_PUBLICADO
    assert publicacao.estado(None, "150000") == publicacao.PUBLICADO
    assert publicacao.estado("22/06/2026") == publicacao.PUBLICADO
    # o snapshot do alerta lê pela MESMA régua da tela
    assert (
        detect_changes.snapshot(
            _proposta(execucao={"situacao_publicacao": "sim"}), hoje=date(2026, 1, 1)
        )["publicada"]
        is False
    )


# ── favoritar é acompanhar ─────────────────────────────────────────────────
async def test_favoritar_cria_acompanhamento_com_linha_de_base(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("fav-monitor@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-FAV", "3550308", situacao="Em análise")
    async with rls_session(u) as s:
        await fav_service.adicionar(s, u, pid)
        mon = (await s.execute(select(Monitoramento))).scalar_one()
        assert mon.origem == "favorito"
        # a fotografia é tirada NA HORA: a mudança que vier depois já alerta,
        # sem esperar uma varredura só para criar a linha de base
        assert mon.snapshot and mon.snapshot["situacao"] == "Em análise"

    async with rls_session(u) as s:
        proposta = (await s.execute(select(Proposta).where(Proposta.id == pid))).scalar_one()
        proposta.situacao = "Aprovada"
        await s.flush()
        await oport_service.varredura(s, await _usuario(s, u))
        alertas = (await s.execute(select(Alerta))).scalars().all()
        assert [a.tipo for a in alertas] == ["situacao"]


async def test_favorita_antiga_entra_no_acompanhamento_na_varredura(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Favorita anterior à feature (sem monitoramento) é adotada pela varredura."""
    u = await seed_user("fav-legado@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-LEG-FAV", "3550308")
    async with rls_session(u) as s:
        # grava o favorito SEM passar pelo serviço (é o estado do banco legado)
        await s.execute(
            text("INSERT INTO favoritos (usuario_id, proposta_id) VALUES (:u, :p)"),
            {"u": u, "p": pid},
        )
        await oport_service.varredura(s, await _usuario(s, u))
        mon = (await s.execute(select(Monitoramento))).scalar_one()
        assert mon.origem == "favorito" and mon.snapshot is not None


async def test_parar_favorita_nao_ressuscita_na_proxima_varredura(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("fav-parou@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-PAROU", "3550308")
    async with rls_session(u) as s:
        await fav_service.adicionar(s, u, pid)
        mon = (await s.execute(select(Monitoramento))).scalar_one()
        await mon_service.desativar(s, u, mon.id)
        await oport_service.varredura(s, await _usuario(s, u))
        mons = (await s.execute(select(Monitoramento))).scalars().all()
        assert len(mons) == 1 and mons[0].ativo is False


async def test_cron_diario_varre_alertas_do_usuario(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """O alerta nasce no CRON: o gestor não precisa abrir a central para saber."""
    from src.jobs import alertas as alertas_job

    u = await seed_user("cron@x.com")
    await seed_municipio(u, "3550308")
    pid = await seed_proposta("transferegov_ff", "P-CRON", "3550308", situacao="Em análise")
    async with rls_session(u) as s:
        await fav_service.adicionar(s, u, pid)

    async with rls_session(u) as s:
        proposta = (await s.execute(select(Proposta).where(Proposta.id == pid))).scalar_one()
        proposta.situacao = "Aprovada"
        await s.flush()

    resumo = await alertas_job.varrer_todos()
    assert resumo["usuarios"] == 1 and resumo["alertas"] == 1
    async with rls_session(u) as s:
        alerta = (await s.execute(select(Alerta))).scalar_one()
        assert alerta.tipo == "situacao"
