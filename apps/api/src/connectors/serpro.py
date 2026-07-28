"""Connector SERPRO — painel público dd-publico (scraping) + API de enrichment.

Fonte principal: o painel público do SERPRO (Qlik, JS pesado) em
https://dd-publico.serpro.gov.br/extensions/painel/painel.html — só renderiza
com browser headless, então a extração usa a facade de scraping
(Crawl4AI/Firecrawl) com schema estruturado. A API gateway do SERPRO (token)
segue como enrichment/cruzamento quando credenciada; se ela falhar ou não
estiver configurada, o painel assume (coleta combinada com fallback).
Campos/rotas isolados p/ calibração.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "transferencias/municipio"  # calibrar (API gateway, requer token)

# schema de extração do painel dd-publico — calibrar contra o painel vivo
PAINEL_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "transferencias": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "programa": {"type": "string"},
                    "orgao": {"type": "string"},
                    "modalidade": {"type": "string"},
                    "situacao": {"type": "string"},
                    "valor": {"type": "string"},
                    "data": {"type": "string"},
                    "numero": {"type": "string"},
                },
            },
        }
    },
}


class SerproConnector:
    source_id = "serpro"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.serpro_base_url

    async def _collect_api(self, municipio_ibge: str) -> list[RawRecord]:
        base = await config_service.resolver("serpro_base_url") or self.base_url
        data = await get_json(base, ENDPOINT, {"ibge": municipio_ibge})
        linhas = data if isinstance(data, list) else data.get("items", [])
        return [
            RawRecord(
                source_id=self.source_id,
                id_externo=str(row.get("id")),
                municipio_ibge=municipio_ibge,
                endpoint=ENDPOINT,
                raw={"enrichment": row},
            )
            for row in linhas
        ]

    async def _collect_painel(self, municipio_ibge: str) -> list[RawRecord]:
        painel = await config_service.resolver("serpro_painel_url") or settings.serpro_painel_url
        scraper = get_scraper()
        dados = await scraper.extract(
            painel,
            PAINEL_EXTRACT_SCHEMA,
            prompt=f"Extraia as transferências do município IBGE {municipio_ibge}.",
        )
        itens = dados.get("transferencias", []) if isinstance(dados, dict) else []
        return [
            RawRecord(
                source_id=self.source_id,
                id_externo=str(item.get("numero") or f"painel-{municipio_ibge}-{i}"),
                municipio_ibge=municipio_ibge,
                endpoint="scrape",
                raw={"plano_acao": item, "scraper": dados.get("_scraper")},
            )
            for i, item in enumerate(itens)
        ]

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        try:
            return await self._collect_api(municipio_ibge)
        except Exception:
            # painel público via scraping headless; se nenhum scraper estiver
            # configurado, propaga o erro original da API (nunca engolir)
            scraper = get_scraper()
            if not await scraper.is_enabled():
                raise
            return await self._collect_painel(municipio_ibge)

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return await get_scraper().is_enabled()


register(SerproConnector())
