"""Connector TransfereGov — Discricionárias e Legais (CSV loader).

Sem API REST: baixa o CSV diário do repositório de dados abertos (SIconv/detru)
e filtra pelo município. As COLUNAS reais variam entre arquivos (VL_GLOBAL_CONV,
Valor Global, vl_empenhado…), então o mapeamento é por PALAVRA-CHAVE, produzindo
o mesmo shape que o normalizador de propostas entende — inclusive o bloco de
EXECUÇÃO financeira (global/empenhado/liberado/pago/saldo), que é o que o
gestor quer ver: quanto foi disponibilizado ao município e ainda não usado.
"""

from __future__ import annotations

import csv
import io
import unicodedata
import zipfile
from datetime import date
from typing import Any

import httpx

from ..core.config import settings
from ..services import config as config_service
from ._http import TIMEOUT
from .base import RawRecord, register

# Fonte oficial: ZIP nacional (siconv_proposta.csv dentro) no Azure blob do
# Transferegov. Tem COD_MUNIC_IBGE, então dá pra filtrar por município.
ZIP_URL = (
    "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip"
)

# o arquivo é NACIONAL (todos os municípios) e grande (~200MB) — cache dos
# BYTES em memória por 1h para a live-search de vários municípios reusar sem
# rebaixar. Guarda bytes (não o texto ~1GB descompactado).
_CACHE_TTL = 3600.0
_fonte_cache: dict[str, tuple[float, bytes]] = {}


def _digits(v: Any) -> str:
    return "".join(c for c in str(v) if c.isdigit())


def _norm(texto: str) -> str:
    sem = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower()


def _col(row: dict, *keywords: str) -> Any:
    """Primeiro valor cuja coluna contém alguma das palavras-chave
    (case-insensitive e sem acento — 'Nº Transferência' casa com 'transferencia')."""
    for k, v in row.items():
        lk = _norm(k)
        if any(_norm(kw) in lk for kw in keywords):
            return v
    return None


def _plano_do_csv(row: dict) -> dict:
    """Linha do CSV → dict no vocabulário do normalizador (com execução)."""
    return {
        "numero": _col(row, "nr_convenio", "transferencia", "numero"),
        "situacao": _col(row, "situa"),
        "modalidade": _col(row, "modalidade"),
        "tipo_transferencia": _col(row, "tipo"),
        "objeto": _col(row, "objeto"),
        "orgao": _col(row, "orgao", "órgão", "repassador"),
        "link": _col(row, "link", "url"),
        "uf": _col(row, "uf"),
        "ente_recebedor": _col(row, "recebedor", "proponente", "convenente"),
        "natureza_juridica": _col(row, "natureza"),
        "ano": _col(row, "ano"),
        "data_assinatura": _col(row, "assinatura"),
        "data_inicio_vigencia": _col(row, "inicio_vig", "início vig", "inicio vig"),
        "data_fim_vigencia": _col(row, "fim_vig", "fim vig"),
        "valor_global": _col(row, "global"),
        "valor_empenhado": _col(row, "empenh"),
        "valor_liberado": _col(row, "liberado", "desembols"),
        "valor_pago": _col(row, "pago"),
        "saldo_conta": _col(row, "saldo"),
        "valor_contrapartida": _col(row, "contrapartida"),
        "csv": row,
    }


class TransferegovDiscConnector:
    source_id = "transferegov_disc"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_disc_csv_url

    def _resolver_url(self, base: str) -> str:
        # a URL antiga (repositorio.dados.gov.br/.../siconv_proposta.csv) 404 —
        # a fonte oficial é o ZIP nacional no Azure blob. Aceita override .csv/.zip.
        low = base.lower()
        if low.endswith(".zip") or low.endswith(".csv"):
            return base
        return ZIP_URL

    async def _bytes_da_fonte(self, url: str) -> bytes:
        import time

        agora = time.monotonic()
        em_cache = _fonte_cache.get(url)
        if em_cache and agora - em_cache[0] < _CACHE_TTL:
            return em_cache[1]
        # ZIP nacional é grande (~200MB); timeout folgado só p/ esta baixada
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=15.0), follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            conteudo = resp.content
        _fonte_cache[url] = (agora, conteudo)
        return conteudo

    def _abrir_csv(self, url: str, conteudo: bytes) -> io.TextIOBase:
        """Stream de texto do CSV — direto ou de dentro do ZIP (sem carregar o
        CSV inteiro em memória: o csv.DictReader consome linha a linha)."""
        if url.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(conteudo))
            nome = next(
                (n for n in z.namelist() if n.lower().endswith(".csv")), z.namelist()[0]
            )
            return io.TextIOWrapper(z.open(nome), encoding="utf-8-sig", errors="replace")
        return io.StringIO(conteudo.decode("utf-8-sig", errors="replace"))

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_disc_csv_url") or self.base_url
        url = self._resolver_url(base)
        conteudo = await self._bytes_da_fonte(url)

        f = self._abrir_csv(url, conteudo)
        header_line = f.readline()
        delim = ";" if header_line.count(";") >= header_line.count(",") else ","
        fieldnames = next(csv.reader([header_line], delimiter=delim))
        reader = csv.DictReader(f, fieldnames=fieldnames, delimiter=delim)

        records: list[RawRecord] = []
        for row in reader:
            ibge_row = _digits(_col(row, "ibge"))
            if not ibge_row or ibge_row not in (municipio_ibge, municipio_ibge[:6]):
                continue
            plano = _plano_do_csv(row)
            id_ext = str(plano.get("numero") or _col(row, "id_proposta") or len(records) + 1)
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=id_ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=url.rsplit("/", 1)[-1],
                    raw={"plano_acao": plano, "modalidade": plano.get("modalidade")},
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.head(self._resolver_url(self.base_url))
            return resp.status_code < 400
        except Exception:
            return False


register(TransferegovDiscConnector())
