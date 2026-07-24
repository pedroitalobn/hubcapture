"""Connector TransfereGov — Transferências Voluntárias (API pública, convênios).

Base: https://api-publica.transferegov.gestao.gov.br/voluntarias/
(docs vivos em <base>/docs — mesmo padrão PostgREST dos demais módulos:
?campo=eq.valor · ?campo=in.(a,b,c) · limit/offset).

Cobre convênios/contratos de repasse das transferências discricionárias e
legais por município — complementa o `transferegov_disc` (CSV diário) com a
consulta on-line. Coleta combinada: API primária; se a API cair, o scraping
(facade Crawl4AI/Firecrawl) assume como fallback.

NOTA: rota e nomes de campo estão isolados em constantes de propósito — são o
ponto de calibração contra os docs vivos da API.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

# ── Rota/campos a calibrar contra <base>/docs ───────────────────────────────
ENDPOINT = "convenio"
IBGE_FIELD = "codigo_ibge_municipio"  # coluna de IBGE do proponente/beneficiário
ID_FIELD = "numero_convenio"  # NR_CONVENIO — chave externa canônica
PAGE_LIMIT = 500


class TransferegovVoluntariasConnector:
    source_id = "transferegov_voluntarias"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_voluntarias_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_voluntarias_base_url") or self.base_url
        try:
            data = await get_json(
                base,
                ENDPOINT,
                {IBGE_FIELD: f"eq.{municipio_ibge}", "limit": str(PAGE_LIMIT)},
            )
            linhas = data if isinstance(data, list) else data.get("items", [])
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(row.get(ID_FIELD) or row.get("id") or i),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={"plano_acao": row, "modalidade": "Convênio"},
                )
                for i, row in enumerate(linhas)
            ]
        except Exception:
            # fallback: scraping da consulta pública (quando algum scraper está ligado)
            scraper = get_scraper()
            if not await scraper.is_enabled():
                raise
            dados = await scraper.scrape(f"{base}{ENDPOINT}?{IBGE_FIELD}=eq.{municipio_ibge}")
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=f"scrape-{municipio_ibge}",
                    municipio_ibge=municipio_ibge,
                    endpoint="scrape",
                    raw={"scrape": dados, "modalidade": "Convênio"},
                )
            ]

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return False


register(TransferegovVoluntariasConnector())
