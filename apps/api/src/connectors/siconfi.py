"""Connector Siconfi/CAUC (conformidade fiscal) — CSV do Tesouro Transparente.

Coleta os requisitos do CAUC (por seção) e o rating CAPAG do município. Base URL
resolvida em runtime pelo painel admin (`siconfi_csv_url`). Campos/rota isolados
em constantes — prontos para calibração contra o CSV oficial.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import httpx

from ..core.config import settings
from ..services import config as config_service
from ._http import TIMEOUT
from .base import RawRecord, register

CAUC_FILE = "cauc.csv"  # calibrar
COL_IBGE = "COD_IBGE"
COL_NUMERO = "NR_REQUISITO"
COL_SECAO = "SECAO"
COL_DESCRICAO = "DESCRICAO"
COL_STATUS = "SITUACAO"
COL_ORGAO = "ORGAO"

# de-para do texto de situação do CSV → status canônico
_STATUS = {
    "comprovado": "comprovado",
    "regular": "comprovado",
    "a comprovar": "a_comprovar",
    "irregular": "a_comprovar",
    "desativado": "desativado",
}


def _status(bruto: str) -> str:
    return _STATUS.get((bruto or "").strip().lower(), "a_comprovar")


class SiconfiConnector:
    source_id = "siconfi"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.siconfi_csv_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("siconfi_csv_url") or self.base_url
        url = f"{base.rstrip('/')}/{CAUC_FILE}"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            texto = resp.text
        reader = csv.DictReader(io.StringIO(texto), delimiter=";")
        records: list[RawRecord] = []
        for row in reader:
            if str(row.get(COL_IBGE, "")).strip() != municipio_ibge:
                continue
            numero = str(row.get(COL_NUMERO) or len(records) + 1)
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=f"cauc:{municipio_ibge}:{numero}",
                    municipio_ibge=municipio_ibge,
                    endpoint=CAUC_FILE,
                    raw={
                        "tipo": "cauc",
                        "numero": numero,
                        "secao": row.get(COL_SECAO),
                        "descricao": row.get(COL_DESCRICAO),
                        "status": _status(row.get(COL_STATUS, "")),
                        "orgao": row.get(COL_ORGAO),
                        "csv": row,
                    },
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            base = await config_service.resolver("siconfi_csv_url") or self.base_url
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.head(base)
            return resp.status_code < 400
        except Exception:
            return False


register(SiconfiConnector())
