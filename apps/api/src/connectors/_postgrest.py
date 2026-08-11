"""Autocalibração compartilhada para módulos PostgREST do TransfereGov.

Os módulos da API pública (especiais, voluntárias, fundo a fundo…) expõem o
próprio schema via OpenAPI (GET <base>/ com Accept: application/openapi+json).
Em vez de chutar rota/coluna em constante — o que quebrou em produção com
42703/404 — descobrimos em runtime:

  - `escolher_endpoint_e_coluna(defs, preferidas)`: dado o dicionário de
    tabelas do spec, escolhe (tabela, coluna_ibge) — preferindo as tabelas da
    lista e, nelas, colunas com 'ibge' no nome (ou código de município).
  - `descobrir(base_url, preferidas)`: baixa o spec e aplica a escolha; cache
    em memória por base_url.
"""

from __future__ import annotations

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# cache (base_url, chave-de-preferências) → (endpoint, coluna_ibge)
_cache: dict[tuple[str, tuple[str, ...]], tuple[str, str]] = {}

# candidatos de coluna de IBGE p/ tentativa direta quando o OpenAPI não ajudar
IBGE_CANDIDATES = (
    "codigo_ibge",
    "cd_ibge",
    "cd_municipio_ibge",
    "codigo_municipio_ibge",
    "id_municipio_ibge",
    "co_municipio_ibge",
    "codigo_ibge_municipio",
    "codigo_ibge_municipio_beneficiario",
    "cd_municipio",
    "codigo_municipio",
)


def escolher_coluna_ibge(colunas: list[str]) -> str | None:
    """'ibge' no nome > código de município (mesma heurística do fundo a fundo)."""
    for c in colunas:
        if "ibge" in c.lower():
            return c
    for c in colunas:
        lc = c.lower()
        if "municipio" in lc and any(k in lc for k in ("cd", "cod", "id")):
            return c
    return None


def escolher_endpoint_e_coluna(defs: dict, preferidas: tuple[str, ...]) -> tuple[str, str] | None:
    """(tabela, coluna_ibge) a partir das definições do OpenAPI do PostgREST."""
    # 1) tabelas preferidas, na ordem
    for tabela in preferidas:
        props = (defs.get(tabela) or {}).get("properties") or {}
        col = escolher_coluna_ibge(list(props))
        if col:
            return tabela, col
    # 2) qualquer tabela com coluna de IBGE — nomes mais "de domínio" primeiro
    ordenadas = sorted(
        defs,
        key=lambda t: (
            not any(kw in t.lower() for kw in ("plano", "convenio", "transfer", "proposta")),
            t,
        ),
    )
    for tabela in ordenadas:
        props = (defs.get(tabela) or {}).get("properties") or {}
        col = escolher_coluna_ibge(list(props))
        if col:
            return tabela, col
    return None


async def descobrir(base_url: str, preferidas: tuple[str, ...]) -> tuple[str, str] | None:
    """Baixa o OpenAPI do módulo e escolhe (endpoint, coluna_ibge). Cacheado."""
    chave = (base_url, preferidas)
    if chave in _cache:
        return _cache[chave]
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
            resp = await client.get("", headers={"Accept": "application/openapi+json"})
            resp.raise_for_status()
            spec = resp.json()
        defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
        escolha = escolher_endpoint_e_coluna(defs, preferidas)
    except Exception:
        return None
    if escolha:
        _cache[chave] = escolha
    return escolha
