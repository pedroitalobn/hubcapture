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
from ._http import get_json
from .base import RawRecord, register

# ── Rota/campos a calibrar contra <base>/docs ───────────────────────────────
ENDPOINT = "plano_acao"
IBGE_FIELD = "codigo_ibge_municipio_beneficiario"  # calibrar
ID_FIELD = "id_plano_acao"


class TransferegovEspConnector:
    source_id = "transferegov_esp"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_esp_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_esp_base_url") or self.base_url
        try:
            data = await get_json(
                base, ENDPOINT, {IBGE_FIELD: f"eq.{municipio_ibge}", "limit": "500"}
            )
            linhas = data if isinstance(data, list) else data.get("items", [])
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(row.get(ID_FIELD) or row.get("id")),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={"plano_acao": row, "modalidade": "Especial"},
                )
                for row in linhas
            ]
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
