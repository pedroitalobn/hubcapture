"""Empenhos da proposta: refiltro, de-para, totais e timeline.

O empenho é o fato que diz se o recurso saiu do papel, então os testes cobrem
justamente onde ele pode sair ERRADO: linha de outra proposta entrando, anulação
somando como se fosse recurso disponível, e o total que a faixa de destaque usa.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

from src.connectors.empenhos_especiais import linha_e_da_proposta
from src.ingestion.normalizer_empenho import normalize_empenho
from src.services import andamento
from src.services import empenhos_proposta as service

# a linha como a rota `/empenhos_especiais` a entrega
LINHA = {
    "id_empenho_especial": 55231,
    "numero_proposta": "14275/2026",
    "id_plano_acao": 123456,
    "numero_empenho_especial": "2026NE000123",
    "data_empenho_especial": "2026-04-15",
    "tipo_empenho_especial": "Ordinário",
    "situacao_empenho_especial": "Emitido",
    "valor_empenhado_empenho_especial": "1.500.000,00",
    "valor_anulado_empenho_especial": 0,
    "valor_pago_empenho_especial": "500000.00",
    "ug_emitente_empenho_especial": "MINISTERIO DA SAUDE",
    "natureza_despesa_empenho_especial": "44.40.51",
}


def test_le_o_empenho_da_rota() -> None:
    e = normalize_empenho(LINHA, fonte="transferegov_empenho")
    assert e.numero_empenho == "2026NE000123"
    assert e.data_empenho == date(2026, 4, 15)
    assert e.tipo_empenho == "Ordinário"
    assert e.situacao == "Emitido"
    # valor em pt-BR não pode virar 150000000
    assert e.valor_empenhado == Decimal("1500000.00")
    assert e.valor_pago == Decimal("500000.00")
    assert e.ug_emitente == "MINISTERIO DA SAUDE"
    assert e.numero_proposta == "14275/2026"
    assert e.ano == "2026"


def test_anulacao_nao_entra_como_valor_empenhado() -> None:
    """Regressão: `valor_anulado...` casa "valor" — lido como empenhado, diria
    que há recurso reservado justamente onde ele foi devolvido."""
    e = normalize_empenho(
        {"valor_anulado_empenho": "900,00", "numero_empenho": "2026NE9"},
        fonte="f",
    )
    assert e.valor_empenhado is None
    assert e.valor_anulado == Decimal("900.00")


def test_identidade_vem_do_id_da_fonte_e_e_estavel() -> None:
    assert normalize_empenho(LINHA, fonte="f").id_externo == "55231"
    sem_id = {k: v for k, v in LINHA.items() if k != "id_empenho_especial"}
    assert normalize_empenho(sem_id, fonte="f").id_externo == "2026NE000123"


def test_hash_muda_quando_o_empenho_e_anulado() -> None:
    a = normalize_empenho(LINHA, fonte="f")
    b = normalize_empenho({**LINHA, "valor_anulado_empenho_especial": "1500000,00"}, fonte="f")
    assert a.hash_conteudo != b.hash_conteudo


def test_le_cabecalho_em_caixa_alta() -> None:
    e = normalize_empenho({"NUMERO_EMPENHO": "2026NE7", "VALOR_EMPENHADO": 10}, fonte="f")
    assert e.numero_empenho == "2026NE7"
    assert e.valor_empenhado == Decimal("10")


# ── o refiltro: nunca ingerir empenho de outra proposta ─────────────────────


def test_reconhece_a_linha_da_propria_proposta() -> None:
    chaves = {"numero_proposta": "14275/2026", "id_plano_acao": "123456"}
    assert linha_e_da_proposta(LINHA, chaves) is True


def test_recusa_linha_de_outra_proposta() -> None:
    """A API pode IGNORAR um query param desconhecido e devolver a tabela
    nacional — sem este filtro, empenho alheio entraria como se fosse daqui."""
    alheia = {**LINHA, "numero_proposta": "99999/2026", "id_plano_acao": 999999}
    assert linha_e_da_proposta(alheia, {"numero_proposta": "14275/2026"}) is False


def test_formatos_diferentes_do_mesmo_numero_casam() -> None:
    """"14275/2026" e "142752026" são o mesmo número em grafias diferentes."""
    assert linha_e_da_proposta(
        {"nr_proposta": "142752026"}, {"numero_proposta": "14275/2026"}
    ) is True


def test_linha_sem_identificacao_fica_indeterminada() -> None:
    """Nem sim nem não: quem chama decide se confia no filtro do servidor."""
    assert linha_e_da_proposta({"valor_empenhado": 10}, {"numero_proposta": "1"}) is None


# ── totais (é o que a faixa de destaque mostra) ─────────────────────────────


class _Emp:
    def __init__(self, **kw):
        for campo in (
            "valor_empenhado",
            "valor_anulado",
            "valor_liquidado",
            "valor_pago",
            "data_empenho",
        ):
            setattr(self, campo, kw.get(campo))


def test_resumo_soma_e_desconta_anulacao() -> None:
    resumo = service.resumir(
        [
            _Emp(valor_empenhado=Decimal("1000"), valor_pago=Decimal("400"),
                 data_empenho=date(2026, 4, 15)),
            _Emp(valor_empenhado=Decimal("500"), valor_anulado=Decimal("500"),
                 data_empenho=date(2026, 6, 1)),
        ]
    )
    assert resumo.total == 2
    # 1000 + 500 empenhados, 500 anulados → 1000 líquidos
    assert resumo.valor_empenhado == Decimal("1000")
    assert resumo.valor_pago == Decimal("400")
    # o número que o gestor persegue: empenhado − pago
    assert resumo.valor_a_utilizar == Decimal("600")
    assert resumo.primeiro_empenho == date(2026, 4, 15)
    assert resumo.ultimo_empenho == date(2026, 6, 1)


def test_resumo_nunca_devolve_empenhado_negativo() -> None:
    resumo = service.resumir([_Emp(valor_empenhado=Decimal("100"), valor_anulado=Decimal("300"))])
    assert resumo.valor_empenhado == Decimal("0")
    assert resumo.valor_a_utilizar == Decimal("0")


def test_resumo_de_lista_vazia_e_zero() -> None:
    assert service.resumir([]).valor_empenhado == Decimal("0")


# ── timeline ────────────────────────────────────────────────────────────────


def test_empenho_vira_evento_datado() -> None:
    ev = andamento.evento_de_empenho(
        _Emp2(
            data_empenho=date(2026, 4, 15),
            numero_empenho="2026NE000123",
            valor_empenhado=Decimal("1500000"),
            ug_emitente="MINISTERIO DA SAUDE",
            tipo_empenho="Ordinário",
        )
    )
    assert ev.tipo == "empenho"
    assert ev.tom == "ok"
    assert "2026NE000123" in ev.titulo
    assert ev.valor == Decimal("1500000")
    assert ev.ator == "MINISTERIO DA SAUDE"


def test_empenho_anulado_nao_sai_como_boa_noticia() -> None:
    total = andamento.evento_de_empenho(
        _Emp2(data_empenho=date(2026, 5, 1), valor_empenhado=Decimal("100"),
              valor_anulado=Decimal("100"))
    )
    assert total.tom == "danger" and "anulado" in total.titulo.lower()

    parcial = andamento.evento_de_empenho(
        _Emp2(data_empenho=date(2026, 5, 1), valor_empenhado=Decimal("100"),
              valor_anulado=Decimal("40"))
    )
    assert parcial.tom == "warn"
    assert parcial.valor == Decimal("60")  # o que sobrou reservado


class _Emp2(_Emp):
    def __init__(self, **kw):
        super().__init__(**kw)
        for campo in ("numero_empenho", "ug_emitente", "tipo_empenho", "natureza_despesa",
                      "situacao"):
            setattr(self, campo, kw.get(campo))


# ── com banco ───────────────────────────────────────────────────────────────


async def test_empenho_alimenta_totais_e_timeline_sob_rls(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Ponta a ponta do que o gestor reclamou: o empenho tem que APARECER —
    como total, como item e como passo da linha do tempo."""

    class ConnectorFake:
        async def collect_por_proposta(self, chaves):
            assert chaves["numero_proposta"] == "14275/2026"
            return [LINHA]

    monkeypatch.setattr(
        "src.services.empenhos_proposta.EmpenhoEspecialConnector", lambda: ConnectorFake()
    )
    monkeypatch.setattr("src.services.pareceres.por_proposta", _sem_pareceres)

    pid = await seed_proposta(
        "transferegov_esp",
        "123456",
        "3550308",
        numero_proposta="14275/2026",
        dados_fonte=json.dumps({"plano_acao": {"id_plano_acao": 123456}}),
    )
    uid = await seed_user("gestor.empenho@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    async with rls_session(uid) as s:
        itens, resumo, coleta = await andamento.empenhos(s, pid, usuario_id=uid)
    assert coleta.status == "ok"
    assert [i.numero_empenho for i in itens] == ["2026NE000123"]
    assert resumo.valor_empenhado == Decimal("1500000.00")
    assert resumo.valor_a_utilizar == Decimal("1000000.00")

    async with rls_session(uid) as s:
        pagina = await andamento.linha_do_tempo(s, pid, usuario_id=uid)
    empenhos = [e for e in pagina.itens if e.tipo == "empenho"]
    assert len(empenhos) == 1
    assert empenhos[0].data == date(2026, 4, 15)


async def _sem_pareceres(session, proposta_id, **kw):
    from src.schemas.parecer import ParecerColeta

    return [], ParecerColeta(status="ok", total=0)


async def test_empenho_de_outro_territorio_nao_vaza(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    class ConnectorFake:
        async def collect_por_proposta(self, chaves):
            return [LINHA]

    monkeypatch.setattr(
        "src.services.empenhos_proposta.EmpenhoEspecialConnector", lambda: ConnectorFake()
    )
    pid = await seed_proposta(
        "transferegov_esp", "123456", "3550308", numero_proposta="14275/2026"
    )
    dono = await seed_user("dono@x.com")
    await seed_municipio(dono, "3550308")
    estranho = await seed_user("estranho@x.com")
    await seed_municipio(estranho, "2611606")

    from src.db.session import rls_session

    async with rls_session(dono) as s:
        await andamento.empenhos(s, pid, usuario_id=dono)
    async with rls_session(estranho) as s:
        assert await andamento.empenhos(s, pid, usuario_id=estranho) is None


async def test_empenho_nao_duplica_entre_coletas(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    class ConnectorFake:
        async def collect_por_proposta(self, chaves):
            return [LINHA]

    monkeypatch.setattr(
        "src.services.empenhos_proposta.EmpenhoEspecialConnector", lambda: ConnectorFake()
    )
    pid = await seed_proposta(
        "transferegov_esp", "123456", "3550308", numero_proposta="14275/2026"
    )
    uid = await seed_user("dupla@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    for _ in range(2):
        async with rls_session(uid) as s:
            itens, resumo, _ = await andamento.empenhos(s, pid, atualizar=True, usuario_id=uid)
    assert len(itens) == 1
    assert resumo.valor_empenhado == Decimal("1500000.00")


async def test_fonte_fora_do_ar_nao_derruba_a_tela(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    class ConnectorMorto:
        async def collect_por_proposta(self, chaves):
            raise RuntimeError("rota fora do ar")

    monkeypatch.setattr(
        "src.services.empenhos_proposta.EmpenhoEspecialConnector", lambda: ConnectorMorto()
    )
    pid = await seed_proposta(
        "transferegov_esp", "123456", "3550308", numero_proposta="14275/2026"
    )
    uid = await seed_user("erro@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    async with rls_session(uid) as s:
        itens, resumo, coleta = await andamento.empenhos(s, pid, usuario_id=uid)
    assert coleta.status == "erro" and "fora do ar" in coleta.erro
    assert itens == [] and resumo.total == 0


async def test_proposta_sem_numero_diz_que_falta_chave(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Sem chave consultável não há como perguntar — e isso não é "não tem empenho".

    `id_externo` só vira `id_plano_acao` quando é INTEIRO: "X-1" não é id de
    plano de ação, e mandá-lo devolveria 422 ou os empenhos do país inteiro.
    """
    pid = await seed_proposta("fns", "X-1", "3550308")
    uid = await seed_user("semchave@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    async with rls_session(uid) as s:
        proposta = await _carregar(s, pid)
        assert service.chaves_da_proposta(proposta) == {}


async def _carregar(session, pid: uuid.UUID):
    from sqlalchemy import select

    from src.models.proposta import Proposta

    return (
        await session.execute(select(Proposta).where(Proposta.id == pid))
    ).scalar_one()
