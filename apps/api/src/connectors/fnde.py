"""Connector FNDE — Fundo Nacional de Educação (API + scraping, merge).

API traz a estrutura; scraping (Firecrawl) enriquece. A coleta combinada roda os
dois e faz merge; se um lado falhar, o outro assume. Campos isolados p/ calibração.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.firecrawl import get_firecrawl
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "api/repasses"  # calibrar
IBGE_FIELD = "codigo_ibge"


class FndeConnector:
    source_id = "fnde"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.fnde_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        data = await get_json(
            self.base_url, ENDPOINT, {IBGE_FIELD: municipio_ibge, "ano": str(since.year)}
        )
        linhas = data if isinstance(data, list) else data.get("items", [])
        records: list[RawRecord] = []
        for row in linhas:
            raw = {
                "data_repasse": row.get("data"),
                "descricao": row.get("programa"),
                "categoria": row.get("grupo"),
                "orgao_superior": "FNDE",
                "natureza": "repasse",
                "valor": row.get("valor"),
                "documento": row.get("ordem_bancaria"),
                "municipio_nome": row.get("razao_social"),
                "api": row,
            }
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(row.get("id") or row.get("ordem_bancaria")),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw=raw,
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return get_firecrawl().enabled


register(FndeConnector())
