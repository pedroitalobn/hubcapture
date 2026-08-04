"""Connector Siconfi/CAUC (conformidade fiscal) — dataset do Tesouro Transparente.

O Tesouro publica o CAUC/CAPAG como DATASET (CKAN), não como API de consulta.
`cauc.csv` fixo deu 404 em produção, então o connector se AUTOCALIBRA:
  - se `siconfi_csv_url` aponta direto para um .csv → baixa;
  - se aponta para uma página de dataset CKAN (…/dataset/<slug>) → resolve o
    recurso CSV real via API do CKAN (`api/3/action/package_show`), preferindo
    recursos com 'cauc' no nome, e cacheia a URL resolvida (1h);
  - as COLUNAS do CSV são achadas por palavra-chave (case-insensitive), então
    mudanças de cabeçalho não quebram a coleta.
"""

from __future__ import annotations

import csv
import io
import time
from datetime import date
from typing import Any

import httpx

from ..core.config import settings
from ..services import config as config_service
from ._http import TIMEOUT, ConnectorClientError
from .base import RawRecord, register

# de-para do texto de situação do CSV → status canônico
_STATUS = {
    "comprovado": "comprovado",
    "regular": "comprovado",
    "adimplente": "comprovado",
    "a comprovar": "a_comprovar",
    "irregular": "a_comprovar",
    "inadimplente": "a_comprovar",
    "desativado": "desativado",
}

_TTL_URL = 3600.0
_url_cache: dict[str, tuple[float, str]] = {}


def _status(bruto: str) -> str:
    return _STATUS.get((bruto or "").strip().lower(), "a_comprovar")


def _digits(v: Any) -> str:
    return "".join(c for c in str(v) if c.isdigit())


def _col(row: dict, *keywords: str) -> Any:
    """Primeiro valor cuja coluna contém alguma das palavras-chave."""
    for k, v in row.items():
        lk = (k or "").lower()
        if any(kw in lk for kw in keywords):
            return v
    return None


async def _resolver_csv_url(base: str) -> str:
    """URL direta do CSV — resolvendo via CKAN quando for página de dataset."""
    limpo = base.rstrip("/")
    if limpo.lower().endswith(".csv"):
        return limpo
    agora = time.monotonic()
    em_cache = _url_cache.get(limpo)
    if em_cache and agora - em_cache[0] < _TTL_URL:
        return em_cache[1]
    if "/dataset/" not in limpo:
        # sem pista de CKAN: tenta o arquivo clássico
        return f"{limpo}/cauc.csv"
    raiz, slug = limpo.split("/dataset/", 1)
    slug = slug.split("/", 1)[0]
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{raiz}/api/3/action/package_show", params={"id": slug})
        resp.raise_for_status()
        pacote = resp.json()
    recursos = (pacote.get("result") or {}).get("resources") or []
    csvs = [
        r
        for r in recursos
        if str(r.get("format", "")).upper() == "CSV"
        or str(r.get("url", "")).lower().endswith(".csv")
    ]
    if not csvs:
        raise ConnectorClientError(
            f"dataset CKAN '{slug}' não tem recurso CSV — ajuste siconfi_csv_url"
        )
    # prefere o recurso que menciona CAUC
    csvs.sort(
        key=lambda r: ("cauc" not in (str(r.get("name", "")) + str(r.get("url", ""))).lower())
    )
    url = str(csvs[0]["url"])
    _url_cache[limpo] = (agora, url)
    return url


class SiconfiConnector:
    source_id = "siconfi"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.siconfi_csv_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("siconfi_csv_url") or self.base_url
        url = await _resolver_csv_url(base)
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            texto = resp.text
        # separador: usa ';' (padrão gov) com fallback para ','
        primeira = texto.splitlines()[0] if texto else ""
        delim = ";" if primeira.count(";") >= primeira.count(",") else ","
        reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
        records: list[RawRecord] = []
        for row in reader:
            ibge_row = _digits(_col(row, "ibge", "cod_mun", "codigo_mun"))
            if not ibge_row or ibge_row not in (municipio_ibge, municipio_ibge[:6]):
                continue
            numero = str(_col(row, "requisito", "item", "nr_") or len(records) + 1)
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=f"cauc:{municipio_ibge}:{numero}",
                    municipio_ibge=municipio_ibge,
                    endpoint=url.rsplit("/", 1)[-1],
                    raw={
                        "tipo": "cauc",
                        "numero": numero,
                        "secao": _col(row, "secao", "seção", "grupo"),
                        "descricao": _col(row, "descricao", "descrição", "nome"),
                        "status": _status(str(_col(row, "situa", "status") or "")),
                        "orgao": _col(row, "orgao", "órgão"),
                        "csv": row,
                    },
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            base = await config_service.resolver("siconfi_csv_url") or self.base_url
            await _resolver_csv_url(base)
            return True
        except Exception:
            return False


register(SiconfiConnector())
