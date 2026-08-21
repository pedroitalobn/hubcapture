"""Autocalibração dos connectors contra as APIs reais (schema variável)."""

from __future__ import annotations

from datetime import date

import pytest

from src.connectors import emendas as emendas_mod
from src.connectors import fpm as fpm_mod
from src.connectors._http import ConnectorClientError
from src.connectors.transferegov_ff import _escolher_coluna_ibge


# ── transferegov_ff: heurística de coluna IBGE sobre o schema real ──────────
def test_escolher_coluna_ibge() -> None:
    assert _escolher_coluna_ibge(["id", "cd_municipio_ibge", "nome"]) == ("cd_municipio_ibge")
    assert _escolher_coluna_ibge(["id", "codigo_municipio", "uf"]) == "codigo_municipio"
    assert _escolher_coluna_ibge(["id", "nome"]) is None


# ── FPM: refiltro defensivo por IBGE + mapeamento genérico ──────────────────
def test_fpm_linha_do_municipio() -> None:
    assert fpm_mod._linha_do_municipio({"cod_ibge": "3550308", "valor": 1}, "3550308")
    assert fpm_mod._linha_do_municipio({"id_ente": 355030, "valor": 1}, "3550308")
    assert not fpm_mod._linha_do_municipio({"cod_ibge": "9999999"}, "3550308")
    assert not fpm_mod._linha_do_municipio({"valor": 1}, "3550308")  # sem coluna IBGE


def test_fpm_montar_raw_deducao_e_data_composta() -> None:
    raw = fpm_mod._montar_raw(
        {"transferencia": "FUNDEB", "valor": "100,50", "ano": 2026, "mes": "7"}
    )
    assert raw["natureza"] == "deducao"
    assert raw["data_repasse"] == "2026-07-01"
    raw2 = fpm_mod._montar_raw({"tipo": "FPM", "valor": 10, "data": "2026-07-10"})
    assert raw2["natureza"] == "credito"
    assert raw2["data_repasse"] == "2026-07-10"


async def test_fpm_collect_tenta_rotas_e_refiltra(monkeypatch) -> None:
    """1ª rota 404 → tenta a próxima; linhas de outros municípios são descartadas."""
    chamadas: list[str] = []

    async def fake_get_json(base, endpoint, params, headers=None):
        chamadas.append(endpoint)
        if endpoint == "metadata-catalog/":
            raise ConnectorClientError("sem catálogo")
        if endpoint == "tt/transferencias":
            raise ConnectorClientError("404")
        if endpoint == "transferencias":
            return {
                "items": [
                    {
                        "cod_ibge": "3550308",
                        "transferencia": "FPM",
                        "valor": 111,
                        "data": "2026-07-01",
                    },
                    {
                        "cod_ibge": "1111111",
                        "transferencia": "FPM",
                        "valor": 999,
                        "data": "2026-07-01",
                    },
                ]
            }
        raise ConnectorClientError("404")

    async def sem_config(_chave):
        return None

    monkeypatch.setattr(fpm_mod.config_service, "resolver", sem_config)
    monkeypatch.setattr(fpm_mod, "get_json", fake_get_json)
    fpm_mod._endpoint_cache.clear()
    conn = fpm_mod.FpmConnector(base_url="http://x/")
    records = await conn.collect("3550308", since=date(2026, 1, 1))
    assert len(records) == 1
    assert records[0].raw["valor"] == 111
    assert fpm_mod._endpoint_cache["http://x/"] == "transferencias"


async def test_fpm_collect_sem_municipio_levanta(monkeypatch) -> None:
    async def fake_get_json(base, endpoint, params, headers=None):
        if endpoint == "metadata-catalog/":
            return {"items": []}
        return {"items": [{"cod_ibge": "1111111", "valor": 1}]}

    async def sem_config2(_chave):
        return None

    monkeypatch.setattr(fpm_mod.config_service, "resolver", sem_config2)
    monkeypatch.setattr(fpm_mod, "get_json", fake_get_json)
    fpm_mod._endpoint_cache.clear()
    conn = fpm_mod.FpmConnector(base_url="http://y/")
    with pytest.raises(ConnectorClientError):
        await conn.collect("3550308", since=date(2026, 1, 1))


# ── emendas: filtro por localidade (a API não filtra por município) ─────────
def test_emendas_da_localidade() -> None:
    assert emendas_mod._da_localidade({"localidadeDoGasto": "FORTALEZA - CE"}, "Fortaleza", "CE")
    assert emendas_mod._da_localidade({"localidadeDoGasto": "SÃO PAULO - SP"}, "Sao Paulo", "SP")
    assert not emendas_mod._da_localidade({"localidadeDoGasto": "FORTALEZA - CE"}, "Sobral", "CE")
    assert not emendas_mod._da_localidade({"localidadeDoGasto": "Nacional"}, "Fortaleza", "CE")


async def test_emendas_collect_pagina_e_filtra(monkeypatch) -> None:
    async def fake_nome_uf(_ibge):
        return ("Fortaleza", "CE")

    paginas = {
        "1": [
            {"codigoEmenda": "E1", "localidadeDoGasto": "FORTALEZA - CE", "valorPago": "1000"},
            {"codigoEmenda": "E2", "localidadeDoGasto": "SOBRAL - CE", "valorPago": "500"},
        ],
        "2": [],
    }

    async def fake_get_json(base, endpoint, params, headers=None):
        return paginas.get(params.get("pagina", "1"), [])

    async def sem_config3(_chave):
        return None

    monkeypatch.setattr(emendas_mod.config_service, "resolver", sem_config3)
    monkeypatch.setattr(emendas_mod.municipios_service, "nome_uf_por_ibge", fake_nome_uf)
    monkeypatch.setattr(emendas_mod, "get_json", fake_get_json)

    conn = emendas_mod.EmendasConnector(base_url="http://z/")

    async def fake_headers():
        return {"chave-api-dados": "x"}

    monkeypatch.setattr(conn, "_headers", fake_headers)
    records = await conn.collect("2304400", since=date(2026, 1, 1))
    assert [r.id_externo for r in records] == ["E1"]


# ── siconfi: resolução de URL e tolerância de colunas ───────────────────────
async def test_siconfi_url_direta_nao_resolve_ckan() -> None:
    from src.connectors.siconfi import _resolver_csv_url

    assert await _resolver_csv_url("http://x/dados/cauc.csv") == "http://x/dados/cauc.csv"


def test_siconfi_status_e_colunas_tolerantes() -> None:
    from src.connectors.siconfi import _col, _status

    assert _status("Comprovado") == "comprovado"
    assert _status("IRREGULAR") == "a_comprovar"
    row = {"COD_IBGE_MUN": "3550308", "DS_REQUISITO": "CND", "SITUACAO_ITEM": "Regular"}
    assert _col(row, "ibge") == "3550308"
    assert _col(row, "descricao", "requisito") == "CND"
    assert _status(str(_col(row, "situa"))) == "comprovado"


# ── especiais/voluntárias: descoberta de endpoint+coluna via OpenAPI ────────
def test_postgrest_escolher_endpoint_e_coluna() -> None:
    from src.connectors._postgrest import escolher_endpoint_e_coluna

    defs = {
        "programa": {"properties": {"id_programa": {}, "nome": {}}},
        "plano_acao": {"properties": {"id_plano_acao": {}, "codigo_ibge_beneficiario": {}}},
    }
    assert escolher_endpoint_e_coluna(defs, ("plano_acao",)) == (
        "plano_acao",
        "codigo_ibge_beneficiario",
    )
    # tabela preferida sem coluna de IBGE → cai para qualquer tabela que tenha
    defs2 = {
        "convenio": {"properties": {"numero_convenio": {}, "cd_municipio_ibge": {}}},
        "zz_outra": {"properties": {"x": {}}},
    }
    assert escolher_endpoint_e_coluna(defs2, ("proposta",)) == (
        "convenio",
        "cd_municipio_ibge",
    )
    assert escolher_endpoint_e_coluna({"t": {"properties": {"x": {}}}}, ("t",)) is None


async def test_esp_collect_com_descoberta(monkeypatch) -> None:
    from src.connectors import transferegov_esp as esp_mod

    async def sem_config(_chave):
        return None

    async def fake_descobrir(base, preferidas):
        return ("plano_acao_especial", "cd_municipio_ibge")

    async def fake_get_json(base, endpoint, params, headers=None):
        assert endpoint == "plano_acao_especial"
        if params.get("cd_municipio_ibge") == "eq.3550308":
            return [{"id_plano_acao": "PA1", "cd_municipio_ibge": "3550308"}]
        return []

    monkeypatch.setattr(esp_mod.config_service, "resolver", sem_config)
    monkeypatch.setattr(esp_mod._postgrest, "descobrir", fake_descobrir)
    monkeypatch.setattr(esp_mod, "get_json", fake_get_json)
    conn = esp_mod.TransferegovEspConnector(base_url="http://esp/")
    records = await conn.collect("3550308", since=date(2026, 1, 1))
    assert [r.id_externo for r in records] == ["PA1"]


async def test_voluntarias_fallback_candidatos_de_coluna(monkeypatch) -> None:
    """Coluna descoberta é recusada (42703) → tenta os candidatos e acha."""
    from src.connectors import transferegov_voluntarias as vol_mod

    async def sem_config(_chave):
        return None

    async def fake_descobrir(base, preferidas):
        return ("convenio", "coluna_errada")

    async def fake_get_json(base, endpoint, params, headers=None):
        if "coluna_errada" in params:
            raise ConnectorClientError("42703")
        if params.get("codigo_ibge") == "eq.3550308":
            return [{"numero_convenio": "CV1"}]
        raise ConnectorClientError("42703")

    monkeypatch.setattr(vol_mod.config_service, "resolver", sem_config)
    monkeypatch.setattr(vol_mod._postgrest, "descobrir", fake_descobrir)
    monkeypatch.setattr(vol_mod, "get_json", fake_get_json)
    conn = vol_mod.TransferegovVoluntariasConnector(base_url="http://vol/")
    records = await conn.collect("3550308", since=date(2026, 1, 1))
    assert [r.id_externo for r in records] == ["CV1"]


# ── FNS: API do ConsultaFNS primária + scraping como 2ª fonte de verdade ────


class _ScraperStub:
    def __init__(self, dados: dict | None = None, falha: Exception | None = None):
        self._dados = dados
        self._falha = falha

    async def is_enabled(self) -> bool:
        return self._falha is None

    async def extract(self, url, schema, prompt=None):
        if self._falha:
            raise self._falha
        return self._dados or {}


def _fns_sem_config(monkeypatch, fns_mod, scraper: _ScraperStub) -> None:
    async def sem_config(_chave):
        return None

    monkeypatch.setattr(fns_mod.config_service, "resolver", sem_config)
    monkeypatch.setattr(fns_mod, "get_scraper", lambda: scraper)
    fns_mod._endpoint_cache.clear()


def test_fns_campo_prioridade_e_flag() -> None:
    from src.connectors import fns as fns_mod

    # prioridade é do keyword, não da ordem das colunas — e "situacao" nunca
    # casa com "acao" (senão o status PAGO viraria descrição)
    row = {"situacao": "PAGO", "no_acao": "Atenção Básica"}
    assert fns_mod._campo(row, "descricao", "acao") == "Atenção Básica"
    assert fns_mod._flag("SIM") and fns_mod._flag("1") and fns_mod._flag(True)
    assert not fns_mod._flag("NÃO") and not fns_mod._flag("") and not fns_mod._flag(None)


def test_fns_montar_raw_caixa_alta() -> None:
    from src.connectors import fns as fns_mod

    raw = fns_mod._montar_raw(
        {
            "NO_ACAO": "Piso da Atenção Básica",
            "DT_OB": "2026-07-10",
            "VL_REPASSE": "1.234,56",
            "NU_PORTARIA": "GM 123/2026",
            "SG_BLOCO": "Custeio",
            "ST_EMENDA": "NAO",
        }
    )
    assert raw["descricao"] == "Piso da Atenção Básica"
    assert raw["data_repasse"] == "2026-07-10"
    assert raw["valor"] == "1.234,56"
    assert raw["documento"] == "GM 123/2026"
    assert raw["categoria"] == "Custeio"
    assert raw["emenda"] is False
    assert raw["orgao_superior"] == "Fundo Nacional de Saúde"


def test_fns_refiltro_por_ibge() -> None:
    from src.connectors import fns as fns_mod

    assert fns_mod._linha_do_municipio({"coMunicipioIbge": "355030"}, "3550308")
    assert fns_mod._linha_do_municipio({"CO_MUNICIPIO": 3550308}, "3550308")
    assert not fns_mod._linha_do_municipio({"coMunicipioIbge": "9999999"}, "3550308")
    assert fns_mod._tem_coluna_ibge({"CO_MUNICIPIO": 1})
    assert not fns_mod._tem_coluna_ibge({"valor": 1})


async def test_fns_collect_api_e_scrape_fundidos(monkeypatch) -> None:
    """API e scraping rodam juntos; pareia pela portaria e funde com proveniência."""
    from src.connectors import fns as fns_mod

    async def fake_get_json(base, endpoint, params, headers=None):
        if endpoint == "":
            return {}
        if endpoint == "proposta/consultar":
            return {
                "items": [
                    {
                        "coMunicipioIbge": "355030",
                        "noAcao": "Atenção Básica",
                        "vlRepasse": "1000,00",
                        "nuPortaria": "123/2026",
                        "dtOb": "2026-07-01",
                    },
                    {  # outro município — o refiltro descarta
                        "coMunicipioIbge": "110001",
                        "noAcao": "Outra",
                        "vlRepasse": "9",
                        "nuPortaria": "999/2026",
                    },
                ]
            }
        raise ConnectorClientError("404")

    scraper = _ScraperStub(
        dados={
            "repasses": [
                {"portaria": "Portaria nº 123/2026", "acao": "Piso da Atenção Básica (painel)"},
                {"portaria": "777/2026", "acao": "Só na página", "valor": "50,00"},
            ]
        }
    )
    _fns_sem_config(monkeypatch, fns_mod, scraper)
    monkeypatch.setattr(fns_mod, "get_json", fake_get_json)

    conn = fns_mod.FnsConnector(base_url="http://pagina/", api_url="http://api/")
    records = await conn.collect("3550308", since=date(2026, 1, 1))

    assert len(records) == 2  # 1 fundido + 1 só-scraping; o de outro município caiu
    fundido = next(r for r in records if r.endpoint == "proposta/consultar+scrape")
    assert fundido.raw["descricao"] == "Piso da Atenção Básica (painel)"  # scrape vence
    assert fundido.raw["valor"] == "1000,00"  # API vence
    assert fundido.raw["_proveniencia"]["descricao"] == "scrape"
    so_scrape = next(r for r in records if r.endpoint == "scrape")
    assert so_scrape.id_externo == "777/2026"
    assert fns_mod._endpoint_cache["http://api/"] == "proposta/consultar"


async def test_fns_collect_api_falha_scrape_assume(monkeypatch) -> None:
    """API fora do ar → scraping vira a fonte primária (nada pior que antes)."""
    from src.connectors import fns as fns_mod
    from src.ingestion.normalizer_repasse import normalize_repasse

    async def api_fora(base, endpoint, params, headers=None):
        raise ConnectorClientError("503")

    scraper = _ScraperStub(
        dados={"repasses": [{"portaria": "5/2026", "acao": "Custeio", "valor": "10,00"}]}
    )
    _fns_sem_config(monkeypatch, fns_mod, scraper)
    monkeypatch.setattr(fns_mod, "get_json", api_fora)

    conn = fns_mod.FnsConnector(base_url="http://pagina/", api_url="http://api/")
    records = await conn.collect("3550308", since=date(2026, 1, 1))
    assert len(records) == 1
    assert records[0].endpoint == "scrape"
    canonico = normalize_repasse(records[0])
    assert canonico.proveniencia["descricao"] == "scrape"
    assert canonico.valor is not None


async def test_fns_collect_ambos_falham_levanta_erro_da_api(monkeypatch) -> None:
    from src.connectors import fns as fns_mod
    from src.scraping.scraper import ScraperNotConfigured

    async def api_fora(base, endpoint, params, headers=None):
        raise ConnectorClientError("503")

    scraper = _ScraperStub(falha=ScraperNotConfigured("sem provider"))
    _fns_sem_config(monkeypatch, fns_mod, scraper)
    monkeypatch.setattr(fns_mod, "get_json", api_fora)

    conn = fns_mod.FnsConnector(base_url="http://pagina/", api_url="http://api/")
    with pytest.raises(ConnectorClientError):
        await conn.collect("3550308", since=date(2026, 1, 1))
