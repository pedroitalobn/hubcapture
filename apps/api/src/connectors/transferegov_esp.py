"""Connector TransfereGov — Transferências Especiais (API instável → fallback scraping).

API PostgREST (mesmo padrão do FF), porém retornou 502 em produção → a coleta
combinada faz fallback para scraping (Firecrawl) quando disponível.
Campos/rotas isolados em constantes — prontos para calibração.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.firecrawl import get_firecrawl
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "plano_acao_especial"  # calibrar
IBGE_FIELD = "codigo_ibge"  # calibrar
PROG_ID = "id_programa_especial"


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
                    id_externo=str(row.get(PROG_ID) or row.get("id")),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={"plano_acao": row, "modalidade": "Especial"},
                )
                for row in linhas
            ]
        except Exception:
            # fallback: scraping do painel gerencial (quando configurado)
            fc = get_firecrawl()
            if not await fc.is_enabled():
                raise
            dados = await fc.scrape(f"{base}#municipio={municipio_ibge}")
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=f"scrape-{municipio_ibge}",
                    municipio_ibge=municipio_ibge,
                    endpoint="firecrawl",
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
