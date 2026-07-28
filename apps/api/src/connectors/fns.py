"""Connector FNS — Fundo Nacional de Saúde (scraping como fonte primária).

O portal de consultas do FNS não expõe API aberta documentada → coleta por
scraping (facade Crawl4AI/Firecrawl) com extração estruturada. Sem nenhum
scraper configurado o connector degrada (erro tratado pelo serviço → sync_runs).
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from .base import RawRecord, register

# schema de extração (o que queremos que o scraper estruture) — calibrar
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "repasses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data": {"type": "string"},
                    "acao": {"type": "string"},
                    "categoria": {"type": "string"},
                    "portaria": {"type": "string"},
                    "valor": {"type": "string"},
                    "emenda": {"type": "boolean"},
                },
            },
        }
    },
}


class FnsConnector:
    source_id = "fns"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.fns_consulta_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        scraper = get_scraper()
        base = await config_service.resolver("fns_consulta_url") or self.base_url
        url = f"{base}?ibge={municipio_ibge}"
        dados = await scraper.extract(url, EXTRACT_SCHEMA)  # levanta se não configurado
        itens = dados.get("repasses", []) if isinstance(dados, dict) else []
        return [
            RawRecord(
                source_id=self.source_id,
                id_externo=str(item.get("portaria") or f"{municipio_ibge}-{i}"),
                municipio_ibge=municipio_ibge,
                endpoint="firecrawl",
                raw={
                    "data_repasse": item.get("data"),
                    "descricao": item.get("acao"),
                    "categoria": item.get("categoria"),
                    "orgao_superior": "Fundo Nacional de Saúde",
                    "natureza": "repasse",
                    "valor": item.get("valor"),
                    "documento": item.get("portaria"),
                    "emenda": bool(item.get("emenda")),
                },
            )
            for i, item in enumerate(itens)
        ]

    async def health_check(self) -> bool:
        return await get_scraper().is_enabled()


register(FnsConnector())
