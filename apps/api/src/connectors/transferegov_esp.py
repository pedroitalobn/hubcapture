"""Connector TransfereGov — Transferências Especiais (API pública + fallback scraping).

Base: https://api-publica.transferegov.gestao.gov.br/especiais/
(docs vivos em <base>/docs — padrão PostgREST: ?campo=eq.valor).

A API antiga (api.transferegov…/transferenciasespeciais) retornou 502 em
produção; a coleta agora aponta para a API pública e mantém o fallback por
scraping (facade Crawl4AI/Firecrawl) quando a API cai.
Campos/rotas isolados em constantes — calibrar contra <base>/docs.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from . import _postgrest
from ._http import ConnectorClientError, get_json
from .base import RawRecord, register

# defaults; a rota/coluna REAIS são descobertas via OpenAPI do PostgREST
# (override manual no painel: transferegov_esp_endpoint / _ibge_field)
ENDPOINT = "plano_acao"
IBGE_FIELD = "codigo_ibge_municipio_beneficiario"
ID_FIELD = "id_plano_acao"
TABELAS_PREFERIDAS = ("plano_acao", "transferencia_especial", "plano_trabalho")


class TransferegovEspConnector:
    source_id = "transferegov_esp"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_esp_base_url

    async def _endpoint_e_coluna(self, base: str) -> tuple[str, str]:
        """Override do painel > OpenAPI do PostgREST > defaults."""
        endpoint = await config_service.resolver("transferegov_esp_endpoint")
        coluna = await config_service.resolver("transferegov_esp_ibge_field")
        if endpoint and coluna:
            return endpoint, coluna
        descoberto = await _postgrest.descobrir(base, TABELAS_PREFERIDAS)
        if descoberto:
            return endpoint or descoberto[0], coluna or descoberto[1]
        return endpoint or ENDPOINT, coluna or IBGE_FIELD

    async def _consultar(
        self, base: str, endpoint: str, coluna: str, ibge: str
    ) -> list[dict]:
        data = await get_json(base, endpoint, {coluna: f"eq.{ibge}", "limit": "500"})
        linhas = data if isinstance(data, list) else data.get("items", [])
        # bases com IBGE de 6 dígitos (sem dígito verificador)
        if not linhas and len(ibge) == 7:
            data = await get_json(
                base, endpoint, {coluna: f"eq.{ibge[:6]}", "limit": "500"}
            )
            linhas = data if isinstance(data, list) else data.get("items", [])
        return linhas

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_esp_base_url") or self.base_url
        try:
            endpoint, coluna = await self._endpoint_e_coluna(base)
            try:
                linhas = await self._consultar(base, endpoint, coluna, municipio_ibge)
            except ConnectorClientError:
                # coluna recusada (42703) → tenta os candidatos conhecidos
                linhas = []
                for candidato in _postgrest.IBGE_CANDIDATES:
                    if candidato == coluna:
                        continue
                    try:
                        linhas = await self._consultar(
                            base, endpoint, candidato, municipio_ibge
                        )
                        break
                    except ConnectorClientError:
                        continue
                else:
                    raise
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(row.get(ID_FIELD) or row.get("id")),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={"plano_acao": row, "modalidade": "Especial"},
                )
                for row in linhas
            ]  # noqa: TRY300
        except Exception:
            # fallback: scraping do painel gerencial (quando algum scraper está ligado)
            scraper = get_scraper()
            if not await scraper.is_enabled():
                raise
            dados = await scraper.scrape(f"{base}#municipio={municipio_ibge}")
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=f"scrape-{municipio_ibge}",
                    municipio_ibge=municipio_ibge,
                    endpoint="scrape",
                    raw={"scrape": dados, "modalidade": "Especial"},
                )
            ]

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return False


register(TransferegovEspConnector())
