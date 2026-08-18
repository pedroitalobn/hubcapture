"""Enriquecimento da proposta: rota calibrada, emenda/parlamentar e timeline.

Sem banco e sem rede: o que se testa aqui é o que decide se o dado entra certo
— a ESCOLHA da rota (a regra que impede trazer o Brasil inteiro), o de-para da
emenda e do autor, e a montagem da linha do tempo.

A rota real do módulo `especiais` não é constante no código (§27): é descoberta
no spec. Por isso os testes exercitam a descoberta contra specs de amostra nos
dois dialetos que o TransfereGov publica, em vez de fixar nome de rota.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from src.connectors import _especiais
from src.connectors.emendas_especiais import (
    CHAVES,
    PALAVRAS_ROTA,
    emendas_do_registro_fonte,
)
from src.ingestion.normalizer_emenda import normalize_emenda
from src.models.proposta import Proposta
from src.schemas.parecer import ParecerRead
from src.services import andamento

# ── specs de amostra ────────────────────────────────────────────────────────
# api-publica/<módulo>: OpenAPI 3, filtro direto, paginação pagina/tamanho
SPEC_OPENAPI3 = {
    "openapi": "3.1.0",
    "paths": {
        "/planos_acao_especiais": {
            "get": {
                "parameters": [
                    {"in": "query", "name": "id_plano_acao"},
                    {"in": "query", "name": "pagina"},
                    {"in": "query", "name": "tamanho_da_pagina"},
                ]
            }
        },
        "/emendas_planos_acao_especiais": {
            "get": {
                "parameters": [
                    {"in": "query", "name": "id_plano_acao"},
                    {"in": "query", "name": "pagina"},
                    {"in": "query", "name": "tamanho_da_pagina"},
                ]
            }
        },
        # rota que FALA de emenda mas não aceita nenhuma chave nossa
        "/emendas_consolidadas": {"get": {"parameters": [{"in": "query", "name": "ano"}]}},
    },
}

# api/<módulo>: PostgREST (swagger 2.0, filtro com eq., colunas = parâmetros)
SPEC_POSTGREST = {
    "swagger": "2.0",
    "definitions": {
        "emenda_plano_acao_especial": {
            "properties": {
                "id_plano_acao": {},
                "nome_parlamentar_emenda_plano_acao": {},
                "valor_emenda": {},
            }
        },
        "plano_acao_especial": {"properties": {"id_plano_acao": {}}},
    },
}


def test_escolhe_a_rota_de_emenda_que_aceita_a_chave() -> None:
    rota = _especiais.escolher_rota(SPEC_OPENAPI3, PALAVRAS_ROTA, CHAVES)
    assert rota is not None
    assert rota.endpoint == "emendas_planos_acao_especiais"
    assert rota.chave == "id_plano_acao"
    assert rota.postgrest is False


def test_ignora_rota_do_assunto_que_nao_filtra_pela_proposta() -> None:
    """Regressão: sem filtro, a rota devolveria o país inteiro como se fosse
    a emenda desta proposta."""
    rota = "/emendas_consolidadas"
    spec = {"openapi": "3.1.0", "paths": {rota: SPEC_OPENAPI3["paths"][rota]}}
    assert _especiais.escolher_rota(spec, PALAVRAS_ROTA, CHAVES) is None


def test_ignora_rota_que_aceita_a_chave_mas_nao_e_do_assunto() -> None:
    rota = "/planos_acao_especiais"
    spec = {"openapi": "3.1.0", "paths": {rota: SPEC_OPENAPI3["paths"][rota]}}
    assert _especiais.escolher_rota(spec, PALAVRAS_ROTA, CHAVES) is None


def test_le_o_dialeto_postgrest() -> None:
    rota = _especiais.escolher_rota(SPEC_POSTGREST, PALAVRAS_ROTA, CHAVES)
    assert rota is not None
    assert rota.endpoint == "emenda_plano_acao_especial"
    assert rota.postgrest is True
    # PostgREST exige o operador no valor — sem o `eq.` a consulta não filtra
    assert rota.filtro("123") == {"id_plano_acao": "eq.123"}
    assert rota.paginacao(2, 50) == {"limit": "50", "offset": "50"}


def test_filtro_e_paginacao_do_dialeto_openapi() -> None:
    rota = _especiais.escolher_rota(SPEC_OPENAPI3, PALAVRAS_ROTA, CHAVES)
    assert rota.filtro("123") == {"id_plano_acao": "123"}
    assert rota.paginacao(2, 50) == {"pagina": "2", "tamanho_da_pagina": "50"}


# ── emenda + parlamentar autor ──────────────────────────────────────────────
# a linha como a rota do módulo a entrega (sufixo da entidade nas colunas)
LINHA_API = {
    "id_emenda_plano_acao": 90871,
    "id_plano_acao": 123456,
    "numero_emenda_plano_acao": "202512340003",
    "ano_emenda_plano_acao": 2025,
    "tipo_emenda_plano_acao": "Individual",
    "nome_parlamentar_emenda_plano_acao": "FULANA DE TAL",
    "sigla_partido_parlamentar_emenda": "XYZ",
    "uf_parlamentar_emenda": "CE",
    "valor_emenda_plano_acao": 1500000.00,
    "valor_empenhado_emenda": "250000,50",
}


def test_le_a_emenda_e_o_autor() -> None:
    from decimal import Decimal

    e = normalize_emenda(LINHA_API, fonte="transferegov_emenda")
    assert e.parlamentar == "FULANA DE TAL"
    assert e.partido == "XYZ"
    assert e.uf_parlamentar == "CE"
    assert e.numero_emenda == "202512340003"
    assert e.ano == 2025
    assert e.tipo_emenda == "Individual"
    assert e.valor == Decimal("1500000.00")
    # valor em pt-BR ("250000,50") não pode virar 25000050
    assert e.valor_empenhado == Decimal("250000.50")
    assert e.numero_plano_acao == "123456"


def test_identidade_vem_do_id_da_fonte() -> None:
    assert normalize_emenda(LINHA_API, fonte="f").id_externo == "90871"


def test_identidade_estavel_sem_id_da_fonte() -> None:
    """Sem id, a chave sintética mantém o upsert estável entre coletas."""
    linha = {k: v for k, v in LINHA_API.items() if k != "id_emenda_plano_acao"}
    a = normalize_emenda(linha, fonte="f")
    b = normalize_emenda(dict(linha), fonte="f")
    assert a.id_externo == b.id_externo
    outro = normalize_emenda({**linha, "nome_parlamentar_emenda_plano_acao": "OUTRA"}, fonte="f")
    assert outro.id_externo != a.id_externo


def test_hash_muda_quando_o_empenho_muda() -> None:
    a = normalize_emenda(LINHA_API, fonte="f")
    b = normalize_emenda({**LINHA_API, "valor_empenhado_emenda": "999,00"}, fonte="f")
    assert a.hash_conteudo != b.hash_conteudo


def test_ano_nao_sai_de_dentro_de_plano() -> None:
    """Regressão: casando por substring, "ano" está dentro de "pl-ANO-" e
    `id_emenda_plano_acao=90871` virava o ano 9087 da emenda."""
    e = normalize_emenda({"id_emenda_plano_acao": 90871}, fonte="f")
    assert e.ano is None


def test_codigo_de_parlamentar_nao_vira_nome() -> None:
    """`codigo_parlamentar` casa 'parlamentar' — não pode ser lido como autor."""
    e = normalize_emenda(
        {"codigo_parlamentar_emenda": 4271, "id_plano_acao": 1}, fonte="f"
    )
    assert e.parlamentar is None
    assert e.codigo_parlamentar == "4271"


def test_le_cabecalho_em_caixa_alta() -> None:
    e = normalize_emenda({"NOME_PARLAMENTAR": "BELTRANO", "NUMERO_EMENDA": "12"}, fonte="f")
    assert e.parlamentar == "BELTRANO"
    assert e.numero_emenda == "12"


# ── retaguarda: a emenda que o próprio plano de ação já carrega ─────────────


def test_extrai_emenda_do_registro_fonte() -> None:
    """Sem rota calibrada o painel ainda diz de quem é a emenda."""
    linhas = emendas_do_registro_fonte(
        {
            "plano_acao": {
                "id_plano_acao": 123456,
                "nome_parlamentar_emenda_plano_acao": "FULANA DE TAL",
                "valor_repasse_emenda_parlamentar": 1500000.0,
                "situacao_plano_acao": "AUTORIZADO",
            }
        }
    )
    assert len(linhas) == 1
    e = normalize_emenda(linhas[0], fonte="f", numero_plano_acao="123456")
    assert e.parlamentar == "FULANA DE TAL"
    assert e.proveniencia["parlamentar"] == "registro_fonte"


def test_registro_fonte_sem_emenda_nao_inventa_registro() -> None:
    assert emendas_do_registro_fonte({"situacao_plano_acao": "AUTORIZADO"}) == []
    assert emendas_do_registro_fonte(None) == []
    # valor solto de emenda, sem autor nem número, não descreve emenda nenhuma
    assert emendas_do_registro_fonte({"valor_emenda": 10}) == []


# ── linha do tempo ──────────────────────────────────────────────────────────


def _parecer(**kw) -> ParecerRead:
    base = dict(
        id=uuid.uuid4(),
        fonte="transferegov_parecer",
        id_externo="1",
        numero_plano_trabalho="988776",
    )
    return ParecerRead(**{**base, **kw})


def test_parecer_vira_evento_com_veredito_na_frente() -> None:
    ev = andamento.evento_de_parecer(
        _parecer(
            data_parecer=date(2026, 6, 1),
            situacao="Solicitar Complementação",
            situacao_analise="Concluída",
            responsavel="RENATA OLIVEIRA",
            esfera="concedente",
            papel="Gestor de Instrumento",
        )
    )
    assert ev.tipo == "parecer"
    assert ev.titulo == "Solicitar Complementação"
    assert ev.tom == "warn"  # complementação exige ação do gestor
    assert ev.ator == "RENATA OLIVEIRA"
    assert "Concedente" in ev.detalhe


def test_analise_em_elaboracao_nao_e_decisao() -> None:
    """Regressão: 'Aprovar' ainda em elaboração pintava de verde como decidido."""
    ev = andamento.evento_de_parecer(
        _parecer(situacao="Aprovar Plano de Trabalho", situacao_analise="Em elaboração")
    )
    assert ev.tom == "neutral"


def test_tom_do_veredito() -> None:
    assert andamento.tom_do_veredito("Aprovar Plano de Trabalho") == "ok"
    assert andamento.tom_do_veredito("Reprovar Plano de Trabalho") == "danger"
    assert andamento.tom_do_veredito("Não se aplica") == "neutral"


def test_marcos_da_proposta_entram_datados() -> None:
    hoje = date.today()
    p = Proposta(
        fonte="transferegov_esp",
        id_externo="1",
        numero_proposta="14275/2026",
        data_proposta=date(2026, 3, 26),
        data_atualizacao_fonte=date(2026, 5, 2),
        situacao="EM ANÁLISE",
        execucao={
            "data_assinatura": "2026-04-01",
            "data_fim_vigencia": (hoje + timedelta(days=5)).isoformat(),
        },
        pendencias=[{"descricao": "Enviar cronograma", "prazo": None}],
    )
    eventos = andamento.marcos_da_proposta(p)
    tipos = {e.tipo for e in eventos}
    assert {"proposta", "vigencia", "pendencia", "atualizacao"} <= tipos

    fim = next(e for e in eventos if e.titulo == "Fim da vigência")
    assert fim.futuro is True
    assert fim.tom == "danger"  # vence em 5 dias


def test_situacao_sem_data_nao_vira_evento() -> None:
    """Evento sem data datado por chute seria cronologia inventada."""
    p = Proposta(fonte="f", id_externo="1", situacao="EM ANÁLISE")
    assert andamento.marcos_da_proposta(p) == []


def test_gate_de_captacao_nao_cobre_o_andamento() -> None:
    """§40: ler o andamento do cache é Meu painel. Se o router inteiro ficasse
    atrás do módulo, desligar a captação apagaria a timeline do detalhe."""
    from src.api.v1 import andamento as router_andamento

    assert not any(
        "require_modulo" in repr(getattr(d, "dependency", d))
        for d in (router_andamento.router.dependencies or [])
    )


def test_ordena_do_mais_recente_e_deixa_sem_data_no_fim() -> None:
    itens = andamento.ordenar(
        [
            andamento.EventoAndamento(data=None, tipo="pendencia", titulo="sem data"),
            andamento.EventoAndamento(data=date(2026, 1, 1), tipo="proposta", titulo="antigo"),
            andamento.EventoAndamento(data=date(2026, 6, 1), tipo="parecer", titulo="recente"),
        ]
    )
    assert [i.titulo for i in itens] == ["recente", "antigo", "sem data"]


# ── com banco: RLS e degradação sem a fonte ─────────────────────────────────

DADOS_FONTE = {
    "plano_acao": {
        "id_plano_acao": 123456,
        "nome_parlamentar_emenda_plano_acao": "FULANA DE TAL",
        "valor_repasse_emenda_parlamentar": 1500000.0,
    }
}


async def _criar_proposta(seed_proposta, ibge: str = "3550308") -> uuid.UUID:
    return await seed_proposta(
        "transferegov_esp",
        "123456",
        ibge,
        numero_proposta="14275/2026",
        data_proposta=date(2026, 3, 26),
        dados_fonte=json.dumps(DADOS_FONTE),
    )


async def test_timeline_so_enxerga_proposta_do_territorio(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """O andamento herda o recorte do RLS: proposta de fora não vaza pela
    timeline — que seria uma porta lateral para o detalhe."""
    monkeypatch.setattr(
        "src.services.pareceres.por_proposta",
        _sem_fonte_pareceres,
    )
    pid = await _criar_proposta(seed_proposta, "3550308")

    de_dentro = await seed_user("dentro@x.com")
    await seed_municipio(de_dentro, "3550308")
    de_fora = await seed_user("fora@x.com")
    await seed_municipio(de_fora, "2611606")

    from src.db.session import rls_session

    async with rls_session(de_dentro) as s:
        pagina = await andamento.linha_do_tempo(s, pid, usuario_id=de_dentro)
    assert pagina is not None
    assert any(e.titulo == "Proposta cadastrada na fonte" for e in pagina.itens)

    async with rls_session(de_fora) as s:
        assert await andamento.linha_do_tempo(s, pid, usuario_id=de_fora) is None


async def _sem_fonte_pareceres(session, proposta_id, **kw):
    from src.schemas.parecer import ParecerColeta

    return [], ParecerColeta(status="ok", total=0)


async def test_emenda_degrada_para_o_registro_fonte(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Fonte fora do ar (ou rota não calibrada) não pode virar seção vazia: o
    plano de ação já traz o parlamentar, e é isso que a tela mostra."""

    class ConnectorMorto:
        async def collect_por_proposta(self, chaves):
            raise RuntimeError("rota não calibrada")

    monkeypatch.setattr(
        "src.services.emendas_proposta.EmendaEspecialConnector", lambda: ConnectorMorto()
    )
    pid = await _criar_proposta(seed_proposta, "3550308")
    uid = await seed_user("gestor@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    async with rls_session(uid) as s:
        resultado = await andamento.emendas(s, pid, usuario_id=uid)
    assert resultado is not None
    itens, coleta = resultado
    assert coleta.status == "ok"
    assert coleta.origem == "registro_fonte"
    # e o incidente da fonte não é engolido — vai junto da resposta
    assert coleta.erro and "não calibrada" in coleta.erro
    assert [i.parlamentar for i in itens] == ["FULANA DE TAL"]


async def test_emenda_nao_duplica_entre_coletas(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Upsert por (fonte, id_externo): coletar de novo atualiza, não duplica."""

    class ConnectorMorto:
        async def collect_por_proposta(self, chaves):
            raise RuntimeError("sem rota")

    monkeypatch.setattr(
        "src.services.emendas_proposta.EmendaEspecialConnector", lambda: ConnectorMorto()
    )
    pid = await _criar_proposta(seed_proposta, "3550308")
    uid = await seed_user("gestor2@x.com")
    await seed_municipio(uid, "3550308")

    from src.db.session import rls_session

    for _ in range(2):
        async with rls_session(uid) as s:
            resultado = await andamento.emendas(s, pid, atualizar=True, usuario_id=uid)
    itens, _ = resultado
    assert len(itens) == 1


def test_emenda_do_registro_fonte_le_a_linha_bruta_do_csv() -> None:
    """A proposta do SIconv guarda a linha do CSV em `csv` (§46). Sem olhar
    ali, o painel caía no texto de erro mesmo com a emenda à vista no
    registro-fonte (ponto 16 do feedback)."""
    from src.connectors.emendas_especiais import emendas_do_registro_fonte

    dados = {
        "plano_acao": {
            "objeto": "Aquisição de equipamento",
            "csv": {
                "NR_EMENDA": "50410003",
                "NOME_PARLAMENTAR": "MARCOS PEREIRA",
                "VL_EMENDA": "500000,00",
            },
        }
    }
    achadas = emendas_do_registro_fonte(dados)
    assert len(achadas) == 1
    assert achadas[0]["NOME_PARLAMENTAR"] == "MARCOS PEREIRA"
    assert achadas[0]["_origem"] == "registro_fonte"


def test_registro_sem_emenda_continua_sem_emenda() -> None:
    from src.connectors.emendas_especiais import emendas_do_registro_fonte

    assert emendas_do_registro_fonte({"plano_acao": {"csv": {"OBJETO": "obra"}}}) == []
