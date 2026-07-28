"""Busca de municípios (IBGE Localidades) para o onboarding conversacional.

O usuário digita o NOME do município na conversa; aqui resolvemos para o código
IBGE de 7 dígitos (chave canônica de território, ver CLAUDE.md). A lista completa
(~5,5k municípios) vem da API pública de Localidades do IBGE e fica cacheada em
memória do processo (TTL longo — a malha municipal muda raramente).

Degradação graciosa: se o IBGE não responder, a busca devolve lista vazia e o
front aceita o código IBGE digitado diretamente (7 dígitos).
"""

from __future__ import annotations

import time
import unicodedata

import httpx

from ..core.config import settings
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
