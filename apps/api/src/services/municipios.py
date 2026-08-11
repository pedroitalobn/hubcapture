"""Município: da busca por NOME (entrada) ao rótulo por NOME (saída).

Duas metades da mesma regra — o município é conhecido pelo nome; o código IBGE
de 7 dígitos é a chave canônica de território (ver CLAUDE.md), não a identidade
que se mostra a gente.

1. ENTRADA (onboarding conversacional): o usuário digita o NOME e resolvemos
   para o código. A malha (~5,5k municípios) vem da API pública de Localidades
   do IBGE, cacheada em memória do processo (TTL longo — muda raramente). Se o
   IBGE não responder, a busca devolve vazio e o front aceita o código digitado.

2. SAÍDA (`rotulo`/`enriquecer`): todo registro se apresenta pelo nome do
   município, com o código como dado secundário. Como o cache multi-fonte nem
   sempre traz `municipio_nome`, a resolução tem três degraus: o próprio
   registro → o território do usuário (`municipios_interesse`, sob RLS) → a UF
   derivada do prefixo do IBGE (offline). Sem nome algum, o rótulo degrada para
   "Município 3550308 (SP)" — rotulado, nunca um número solto.
"""

from __future__ import annotations

import time
import unicodedata
from collections.abc import Sequence
from typing import TypeVar

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.municipio_interesse import MunicipioInteresse
from . import config as config_service

ENDPOINT = "municipios"
_TTL_SEGUNDOS = 24 * 3600
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

_cache: list[dict] | None = None
_cache_em: float = 0.0


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sem_acento if unicodedata.category(c) != "Mn").lower()


async def _carregar() -> list[dict]:
    """Baixa a malha municipal (view nivelada) e materializa o índice de busca."""
    global _cache, _cache_em
    if _cache is not None and (time.monotonic() - _cache_em) < _TTL_SEGUNDOS:
        return _cache

    base = await config_service.resolver("ibge_localidades_url") or (settings.ibge_localidades_url)
    async with httpx.AsyncClient(base_url=base, timeout=_TIMEOUT) as client:
        resp = await client.get(ENDPOINT, params={"view": "nivelado"})
        resp.raise_for_status()
        linhas = resp.json()

    municipios = []
    for row in linhas:
        ibge = str(row.get("municipio-id") or "")
        nome = row.get("municipio-nome") or ""
        uf = row.get("UF-sigla") or ""
        if len(ibge) == 7 and nome:
            municipios.append({"ibge": ibge, "nome": nome, "uf": uf, "busca": _normalizar(nome)})
    _cache, _cache_em = municipios, time.monotonic()
    return municipios


async def buscar(q: str, *, limite: int = 8) -> list[dict]:
    """Top-N municípios cujo nome casa com `q` (prefixo antes de substring)."""
    q = q.strip()
    if len(q) < 2:
        return []
    try:
        municipios = await _carregar()
    except Exception:  # IBGE fora do ar → degrada; front aceita código direto
        return []

    if q.isdigit():
        return [
            {k: m[k] for k in ("ibge", "nome", "uf")} for m in municipios if m["ibge"].startswith(q)
        ][:limite]

    alvo = _normalizar(q)
    prefixo = [m for m in municipios if m["busca"].startswith(alvo)]
    contem = [m for m in municipios if alvo in m["busca"] and not m["busca"].startswith(alvo)]
    return [{k: m[k] for k in ("ibge", "nome", "uf")} for m in (prefixo + contem)[:limite]]


async def nome_uf_por_ibge(ibge: str) -> tuple[str, str] | None:
    """(nome, UF) do município — usado por connectors que filtram por NOME
    (ex.: emendas do Portal da Transparência, cuja API não filtra por IBGE)."""
    try:
        municipios = await _carregar()
    except Exception:
        return None
    for m in municipios:
        if m["ibge"] == ibge:
            return m["nome"], m["uf"]
    return None


# ── Saída: o nome lidera, o código apoia ────────────────────────────────────

# Os 2 primeiros dígitos do código IBGE são o código da UF — dá para derivar a
# sigla sem rede nem tabela auxiliar (usado quando o nome não veio da fonte).
UF_POR_PREFIXO_IBGE: dict[str, str] = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

# mapa ibge -> (nome, uf)
Territorio = dict[str, tuple[str | None, str | None]]

M = TypeVar("M", bound=BaseModel)


def uf_do_ibge(ibge: str | None) -> str | None:
    """Sigla da UF derivada do prefixo do código IBGE (offline)."""
    if not ibge or len(ibge) < 2:
        return None
    return UF_POR_PREFIXO_IBGE.get(ibge[:2])


def rotulo(nome: str | None = None, uf: str | None = None, ibge: str | None = None) -> str:
    """Rótulo humano do município — o topo da hierarquia visual do registro.

    Com nome: "São Paulo/SP". Sem nome: "Município 3550308 (SP)" — o número
    aparece, mas rotulado, nunca cru.
    """
    sigla = uf or uf_do_ibge(ibge)
    if nome:
        return f"{nome}/{sigla}" if sigla else nome
    if ibge:
        return f"Município {ibge} ({sigla})" if sigla else f"Município {ibge}"
    return "Município não informado"


async def mapa_territorio(session: AsyncSession) -> Territorio:
    """Nomes/UFs dos municípios que o usuário acompanha (o RLS já recorta)."""
    rows = (await session.execute(select(MunicipioInteresse))).scalars()
    return {m.ibge: (m.nome, m.uf) for m in rows}


def _aplicar(item: M, mapa: Territorio) -> M:
    campos = type(item).model_fields
    ibge = getattr(item, "municipio_ibge", None)
    if not ibge:
        return item

    nome_territorio, uf_territorio = mapa.get(ibge, (None, None))
    update: dict[str, str] = {}
    if "municipio_nome" in campos and not getattr(item, "municipio_nome", None):
        if nome_territorio:
            update["municipio_nome"] = nome_territorio
    if "uf" in campos and not getattr(item, "uf", None):
        sigla = uf_territorio or uf_do_ibge(ibge)
        if sigla:
            update["uf"] = sigla
    return item.model_copy(update=update) if update else item


async def enriquecer(
    session: AsyncSession, itens: Sequence[M], *, mapa: Territorio | None = None
) -> list[M]:
    """Completa `municipio_nome`/`uf` ausentes para que o nome possa liderar.

    Só afeta a resposta da API (`model_copy`) — não persiste nem marca o ORM
    como sujo. Passe `mapa` para reaproveitar a consulta em respostas aninhadas.
    """
    itens = list(itens)
    if not itens:
        return itens
    if mapa is None:
        mapa = await mapa_territorio(session)
    return [_aplicar(i, mapa) for i in itens]
