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
