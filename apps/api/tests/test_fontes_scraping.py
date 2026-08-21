"""Recorte de duas fontes (TransfereGov + FNS), extração de tabela e coleta combinada.

Cobre o que o corte da v1 introduziu: a expansão de grupo → connectors no
onboarding, o parser de tabela/grid que faz o painel Qlik render dado, e a
aglutinação API + scraping (que deixou de ser fallback).
"""

from __future__ import annotations

from src.connectors import _combinada
from src.connectors.base import RawRecord
from src.ingestion.merge import merge_record
from src.scraping import tabelas
from src.services import fontes as fontes_service

# ── Recorte de fontes ───────────────────────────────────────────────────────


def test_grupos_do_onboarding_expandem_para_connectors() -> None:
    assert fontes_service.expandir(["transferegov"]) == list(fontes_service.TRANSFEREGOV)
    # o grupo FNS expande para as DUAS granularidades que a fonte publica:
    # repasse (`fns`) e proposta individual (`fns_propostas`)
    assert fontes_service.expandir(["fns"]) == list(fontes_service.FNS)
    # a escolha das duas cobre exatamente o recorte habilitado
    assert fontes_service.expandir(["fnde"]) == list(fontes_service.FNDE)
    assert fontes_service.expandir(["transferegov", "fns", "fnde"]) == list(
        fontes_service.HABILITADAS
    )


def test_expandir_aceita_connector_id_e_descarta_fonte_desligada() -> None:
    # perfil gravado antes do corte guarda connector id, não grupo
    assert fontes_service.expandir(["transferegov_ff"]) == ["transferegov_ff"]
    # fonte fora do recorte (FPM, emendas, obras) simplesmente não entra
    assert fontes_service.expandir(["fpm", "emendas", "sismob"]) == []
    assert fontes_service.expandir(["fns", "fpm"]) == list(fontes_service.FNS)
    assert fontes_service.expandir(None) == []


def test_painel_visao_geral_pertence_ao_grupo_transferegov() -> None:
    # o painel é servido pelo SERPRO, mas o DADO é TransfereGov
    assert fontes_service.grupo_de("serpro") == "transferegov"
    assert fontes_service.rotulo("serpro") == "TransfereGov"
    assert "serpro" in fontes_service.CAPTACAO


def test_eixos_nao_se_misturam() -> None:
    # captação produz propostas; recebidos produz repasses — nenhuma fonte nos dois
    assert not set(fontes_service.CAPTACAO) & set(fontes_service.RECEBIDOS)


# ── Extração de tabela (o que faz o painel Qlik virar dado) ─────────────────

_GRID_ARIA = """
<div role="grid">
  <div role="row">
    <div role="columnheader">Nº Transferência</div>
    <div role="columnheader">Situação</div>
    <div role="columnheader">Valor Empenhado</div>
  </div>
  <div role="row">
    <div role="gridcell"><span>901231/2024</span></div>
    <div role="gridcell">Em execução</div>
    <div role="gridcell">R$ 10.000,00</div>
  </div>
</div>
"""


def test_le_grid_aria_do_painel_qlik() -> None:
    """Regressão: fechar no primeiro </div> encerrava o grid na 1ª célula."""
    lidas = tabelas.linhas_de_html(_GRID_ARIA)
    assert lidas == [
        [
            {
                "Nº Transferência": "901231/2024",
                "Situação": "Em execução",
                "Valor Empenhado": "R$ 10.000,00",
            }
        ]
    ]


def test_le_table_html_classica() -> None:
    html = "<table><tr><th>Ano</th><th>Valor</th></tr><tr><td>2024</td><td>10</td></tr></table>"
    assert tabelas.linhas_de_html(html) == [[{"Ano": "2024", "Valor": "10"}]]


def test_html_quebrado_nao_derruba_o_parser() -> None:
    assert tabelas.linhas_de_html("<div></div></div><table><tr><td>só") == []
    assert tabelas.linhas_de_html("") == []


def test_cabecalho_casa_com_campo_do_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "transferencias": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "numero": {"type": "string", "description": "Nº Transferência"},
                        "situacao": {"type": "string"},
                        "valor_empenhado": {"type": "string"},
                    },
                },
            }
        },
    }
    chave, campos = tabelas.alvo_do_schema(schema)
    assert chave == "transferencias"

    linha = tabelas.maior_tabela(tabelas.linhas_de_html(_GRID_ARIA))[0]
    mapeada = tabelas.mapear(linha, campos)
    assert mapeada["numero"] == "901231/2024"  # casou pela `description`
    assert mapeada["situacao"] == "Em execução"  # casou sem acento
    assert mapeada["valor_empenhado"] == "R$ 10.000,00"  # casou por palavra
    assert mapeada["_linha"] == linha  # nada é perdido para calibração


# ── Coleta combinada (API + scraping como duas fontes de verdade) ───────────


def test_aglutina_por_numero_ignorando_formatacao() -> None:
    api = [{"numero_proposta": "9012312024", "valor_global": "100"}]
    scrape = [{"numero": "901231/2024", "situacao": "Em execução"}]

    pares = _combinada.aglutinar(api, scrape)

    assert len(pares) == 1
    linha_api, linha_scrape = pares[0]
    assert linha_api["valor_global"] == "100"
    assert linha_scrape["situacao"] == "Em execução"


def test_linha_so_do_scraping_entra_sozinha() -> None:
    """A página conhece transferência que a API ainda não publicou."""
    pares = _combinada.aglutinar(
        [{"numero_proposta": "111"}],
        [{"numero": "222", "situacao": "Nova"}],
    )
    assert len(pares) == 2
    assert ({}, {"numero": "222", "situacao": "Nova"}) in pares


def test_merge_record_aglutina_e_registra_proveniencia() -> None:
    """Situação vem da página (mais atual); valor vem da API (autoritativo)."""
    record = RawRecord(
        source_id="serpro",
        id_externo="901231",
        municipio_ibge="3550308",
        endpoint="transferencias/municipio",
        raw={
            "plano_acao": {"numero": "901231", "situacao": "Em análise", "valor_global": "1000"},
            _combinada.CHAVE_SCRAPE: {"plano_acao": {"situacao": "Em execução"}},
        },
    )

    canonica = merge_record(record)

    assert canonica.situacao == "Em execução"
    assert canonica.proveniencia["situacao"] == "scrape"
    assert canonica.proveniencia["_fonte"] == "serpro"


async def test_coletar_roda_os_dois_lados_e_nenhum_derruba_o_outro() -> None:
    async def api_ok() -> list[dict]:
        return [{"numero": "1"}]

    async def scrape_quebrado() -> list[dict]:
        raise RuntimeError("scraper fora do ar")

    linhas_api, linhas_scrape, erro = await _combinada.coletar(
        api_ok, scrape_quebrado, fonte="serpro"
    )
    assert linhas_api == [{"numero": "1"}] and linhas_scrape == [] and erro is None


async def test_api_fora_do_ar_o_scraping_assume_e_o_erro_fica_disponivel() -> None:
    async def api_quebrada() -> list[dict]:
        raise RuntimeError("502 da fonte")

    async def scrape_ok() -> list[dict]:
        return [{"numero": "2"}]

    linhas_api, linhas_scrape, erro = await _combinada.coletar(
        api_quebrada, scrape_ok, fonte="serpro"
    )
    assert linhas_api == []
    assert linhas_scrape == [{"numero": "2"}]
    assert isinstance(erro, RuntimeError)  # o connector decide se releva


def test_merge_record_sem_scraping_e_normalize_puro() -> None:
    record = RawRecord(
        source_id="transferegov_ff",
        id_externo="1",
        municipio_ibge="3550308",
        endpoint="plano_acao",
        raw={"plano_acao": {"situacao": "Em análise"}},
    )
    canonica = merge_record(record)
    assert canonica.situacao == "Em análise"
    assert canonica.proveniencia["situacao"] == "api"
