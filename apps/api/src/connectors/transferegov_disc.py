"""Connector TransfereGov — Discricionárias e Legais (CSV loader).

Sem API REST: baixa o CSV diário do repositório de dados abertos (SIconv/detru)
e filtra pelo município. As COLUNAS reais variam entre arquivos (VL_GLOBAL_CONV,
Valor Global, vl_empenhado…), então o mapeamento é por PALAVRA-CHAVE, produzindo
o mesmo shape que o normalizador de propostas entende — inclusive o bloco de
EXECUÇÃO financeira (global/empenhado/liberado/pago/saldo), que é o que o
gestor quer ver: quanto foi disponibilizado ao município e ainda não usado.
"""

from __future__ import annotations

import asyncio
import csv
import io
import time
import unicodedata
import zipfile
from datetime import date
from typing import Any

import httpx

from ..core.config import settings
from ..services import config as config_service
from . import _identidade
from ._http import TIMEOUT
from .base import RawRecord, register

# Fonte oficial: ZIP nacional (siconv_proposta.csv dentro) no Azure blob do
# Transferegov. Tem COD_MUNIC_IBGE, então dá pra filtrar por município.
ZIP_URL = "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip"

# o arquivo é NACIONAL (todos os municípios) e grande (~200MB) — cache dos
# BYTES em memória por 1h para a live-search de vários municípios reusar sem
# rebaixar. Guarda bytes (não o texto ~1GB descompactado).
_CACHE_TTL = 3600.0
_fonte_cache: dict[str, tuple[float, bytes]] = {}
# resultado do PARSE por (url, município): varrer o CSV nacional custa minutos
# de CPU — sem este cache, cada busca do painel reparseava o arquivo inteiro.
_registros_cache: dict[tuple[str, str], tuple[float, list[RawRecord]]] = {}
# N buscas simultâneas não podem baixar N × 200MB do mesmo arquivo
_download_lock = asyncio.Lock()


def limpar_cache() -> None:
    """Zera bytes e parse cacheados (testes/ops)."""
    _fonte_cache.clear()
    _registros_cache.clear()


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


def _col_exata(row: dict, *nomes: str) -> Any:
    """Valor da coluna cujo nome normalizado é EXATAMENTE um dos pedidos.

    Necessário para as colunas do SIconv que são prefixo umas das outras:
    por substring, 'dia_prop' casaria também com DIA_PROPOSTA.
    """
    chaves = {_norm(k).strip(): v for k, v in row.items() if isinstance(k, str)}
    for nome in nomes:
        if chaves.get(nome) not in (None, ""):
            return chaves[nome]
    return None


def _plano_do_csv(row: dict) -> dict:
    """Linha do CSV → dict no vocabulário do normalizador (com execução)."""
    return {
        "numero": _col(row, "nr_convenio", "transferencia", "numero"),
        # SIconv/detru (siconv_proposta.csv): a REFERÊNCIA da proposta vem em
        # colunas próprias — NR_PROPOSTA (o nº que o gestor digita no portal) e
        # a data de criação decomposta em DIA_PROP/MES_PROP/ANO_PROP. Sem este
        # de-para o normalizador caía em retaguardas erradas (vigência,
        # exercício) e o painel mostrava ano/data que não são os da proposta.
        "nr_proposta": _col_exata(row, "nr_proposta"),
        "dia_prop": _col_exata(row, "dia_prop"),
        "mes_prop": _col_exata(row, "mes_prop"),
        "ano_prop": _col_exata(row, "ano_prop"),
        "dia_proposta": _col_exata(row, "dia_proposta"),
        # órgão por extenso — a palavra-chave "orgao" pescava COD_ORGAO_SUP
        # (código numérico) e a tela mostrava número onde vai o ministério
        "desc_orgao": _col_exata(row, "desc_orgao"),
        "desc_orgao_superior": _col_exata(row, "desc_orgao_sup", "desc_orgao_superior"),
        "situacao": _col(row, "situa", "sit_proposta"),
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
        def _fresco() -> bytes | None:
            em_cache = _fonte_cache.get(url)
            if em_cache and time.monotonic() - em_cache[0] < _CACHE_TTL:
                return em_cache[1]
            return None

        conteudo = _fresco()
        if conteudo is not None:
            return conteudo
        async with _download_lock:
            conteudo = _fresco()  # outra coleta pode ter baixado enquanto esperávamos
            if conteudo is not None:
                return conteudo
            # ZIP nacional é grande (~200MB); timeout folgado só p/ esta baixada
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(180.0, connect=15.0), follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                conteudo = resp.content
            _fonte_cache[url] = (time.monotonic(), conteudo)
            return conteudo

    def _abrir_csv(self, url: str, conteudo: bytes) -> io.TextIOBase:
        """Stream de texto do CSV — direto ou de dentro do ZIP (sem carregar o
        CSV inteiro em memória: o csv.DictReader consome linha a linha)."""
        if url.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(conteudo))
            nome = next((n for n in z.namelist() if n.lower().endswith(".csv")), z.namelist()[0])
            return io.TextIOWrapper(z.open(nome), encoding="utf-8-sig", errors="replace")
        return io.StringIO(conteudo.decode("utf-8-sig", errors="replace"))

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_disc_csv_url") or self.base_url
        url = self._resolver_url(base)

        em_cache = _registros_cache.get((url, municipio_ibge))
        if em_cache and time.monotonic() - em_cache[0] < _CACHE_TTL:
            return em_cache[1]

        conteudo = await self._bytes_da_fonte(url)
        # o parse varre o arquivo nacional inteiro (CPU puro, minutos) — vai
        # para uma thread; no event loop ele pararia a API TODA enquanto roda
        records = await asyncio.to_thread(self._filtrar_municipio, url, conteudo, municipio_ibge)
        _registros_cache[(url, municipio_ibge)] = (time.monotonic(), records)
        return records

    def _filtrar_municipio(self, url: str, conteudo: bytes, municipio_ibge: str) -> list[RawRecord]:
        """Varre o CSV nacional e devolve só as linhas do município (síncrono)."""
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
            # sem NR_PROPOSTA nem ID_PROPOSTA, a identidade sai do CONTEÚDO da
            # linha e é escopada no município. O contador posicional anterior
            # (`len(records) + 1`) dava "1", "2", "3"… para TODO município — e o
            # par único (fonte, id_externo) é global: a proposta "1" de um
            # município sobrescrevia a "1" do outro e mudava de território.
            # ID_PROPOSTA é a chave primária que a fonte publica para ESTE
            # arquivo, e é ela que manda (§51). O nº do convênio vinha antes e
            # isso instabilizava a identidade: a proposta nasce sem convênio
            # (id = hash do conteúdo) e ganha um ao ser celebrada — a linha
            # trocava de `id_externo` e virava DUAS no painel. Vale também para
            # convergir com a carga do pacote (`jobs/siconv_diario`), que casa
            # pelo mesmo id.
            id_ext = str(
                _col_exata(row, "id_proposta") or plano.get("numero") or ""
            ) or _identidade.hash_conteudo(row, municipio_ibge, prefixo="csv:")
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
