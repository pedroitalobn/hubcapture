"""Connector TransfereGov — Discricionárias e Legais (CSV loader).

Sem API REST: baixa o CSV diário do repositório de dados abertos, parseia e
filtra pelo município. Colunas isoladas em constantes — prontas para calibração.
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

# colunas do CSV `detru` (calibrar contra o arquivo real)
COL_IBGE = "COD_IBGE"
COL_CONVENIO = "NR_CONVENIO"
COL_PROPOSTA = "ID_PROPOSTA"
CSV_FILENAME = "siconv_proposta.csv"  # calibrar


class TransferegovDiscConnector:
    source_id = "transferegov_disc"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_disc_csv_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_disc_csv_url") or self.base_url
        url = f"{base.rstrip('/')}/{CSV_FILENAME}"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            texto = resp.text
        reader = csv.DictReader(io.StringIO(texto), delimiter=";")
        records: list[RawRecord] = []
        for row in reader:
            if str(row.get(COL_IBGE, "")).strip() != municipio_ibge:
                continue
            id_ext = str(row.get(COL_PROPOSTA) or row.get(COL_CONVENIO))
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=id_ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=CSV_FILENAME,
                    raw={"csv": row, "modalidade": "Discricionária"},
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.head(self.base_url)
            return resp.status_code < 400
        except Exception:
            return False


register(TransferegovDiscConnector())
