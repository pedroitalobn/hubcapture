"""Connector SERPRO — enrichment/cruzamento (API direta).

Não é fonte primária de proposta: enriquece/cruza dados existentes. Requer
credenciais SERPRO (token). Campos/rota isolados p/ calibração.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "transferencias/municipio"  # calibrar


class SerproConnector:
    source_id = "serpro"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.serpro_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        data = await get_json(self.base_url, ENDPOINT, {"ibge": municipio_ibge})
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

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return False


register(SerproConnector())
