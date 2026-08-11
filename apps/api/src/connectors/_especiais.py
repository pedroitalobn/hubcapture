"""Autocalibração de rota nos módulos da API pública do TransfereGov.

O enriquecimento da proposta (emenda, parlamentar autor, análise) mora em rotas
IRMÃS da que traz o plano de ação, e o nome delas não é adivinhável — chutar
rota é exatamente o que quebrou em produção (§27). Aqui a rota é DESCOBERTA no
spec do próprio módulo (`<base>/openapi.json` é o que a página `/docs` consome)
e só é aceita com DUAS evidências:

  1. o nome casa o assunto ("emenda", "parlamentar", "analise"…);
  2. a rota aceita uma das chaves que temos em mãos (id_plano_acao,
     numero_proposta, id_plano_trabalho…).

A segunda evidência é a que protege o gestor: rota que casa o nome mas não
aceita a chave devolveria o Brasil inteiro paginado em vez da emenda desta
proposta — e o painel mostraria emenda de outro município como se fosse dele.

Cobre os dois dialetos que o TransfereGov publica:
  - **OpenAPI 3** (`api-publica/<módulo>`): filtro direto `?id_plano_acao=123`,
    paginação `pagina`/`tamanho_da_pagina`;
  - **PostgREST/Swagger 2** (`api/<módulo>`): filtro `?id_plano_acao=eq.123`,
    paginação `limit`/`offset`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# paginação — nomes usados por cada dialeto
PAGINA_OPENAPI = ("pagina", "page")
TAMANHO_OPENAPI = ("tamanho_da_pagina", "tamanho_pagina", "por_pagina", "page_size")

# cache: base_url → spec | None (None = já tentei e não veio)
_spec_cache: dict[str, dict | None] = {}
# cache: (base_url, palavras, chaves) → Rota | None
_rota_cache: dict[tuple[str, tuple[str, ...], tuple[str, ...]], Rota | None] = {}


def limpar_cache() -> None:
    """Zera o que foi descoberto (testes; recalibração após mexer no painel)."""
    _spec_cache.clear()
    _rota_cache.clear()


def _norm(texto: str) -> str:
    sem = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower()


@dataclass(frozen=True)
class Rota:
    """Uma rota calibrada: por onde consultar, com qual chave e como paginar."""

    endpoint: str
    chave: str
    postgrest: bool = False
    param_pagina: str | None = None
    param_tamanho: str | None = None

    def filtro(self, valor: str) -> dict[str, str]:
        """PostgREST exige o operador no valor (`eq.123`); OpenAPI 3 é direto."""
        return {self.chave: f"eq.{valor}" if self.postgrest else str(valor)}

    def paginacao(self, pagina: int, tamanho: int) -> dict[str, str]:
        if self.postgrest:
            return {"limit": str(tamanho), "offset": str((pagina - 1) * tamanho)}
        if not self.param_pagina or not self.param_tamanho:
            return {}
        return {self.param_pagina: str(pagina), self.param_tamanho: str(tamanho)}


async def carregar_spec(base_url: str) -> dict | None:
    """Baixa o spec do módulo. `openapi.json` (FastAPI) e, se não, a raiz
    (PostgREST responde o swagger na raiz com o Accept certo)."""
    if base_url in _spec_cache:
        return _spec_cache[base_url]

    spec: dict | None = None
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
            for caminho, headers in (
                ("openapi.json", {"Accept": "application/json"}),
                ("", {"Accept": "application/openapi+json"}),
            ):
                try:
                    resp = await client.get(caminho, headers=headers)
                    if resp.status_code >= 400:
                        continue
                    corpo = resp.json()
                except Exception:  # noqa: BLE001 — spec ruim não derruba a coleta
                    continue
                if isinstance(corpo, dict) and (corpo.get("paths") or corpo.get("definitions")):
                    spec = corpo
                    break
    except Exception:  # noqa: BLE001 — fonte fora do ar: quem chama decide o fallback
        spec = None

    _spec_cache[base_url] = spec
    return spec


def _e_postgrest(spec: dict) -> bool:
    """Swagger 2.0 com `definitions` de tabela = PostgREST (filtro com `eq.`)."""
    return str(spec.get("swagger", "")).startswith("2") and bool(spec.get("definitions"))


def rotas_do_spec(spec: dict) -> dict[str, set[str]]:
    """endpoint (sem barra) → parâmetros de consulta que ele aceita."""
    rotas: dict[str, set[str]] = {}

    if _e_postgrest(spec):
        # PostgREST aceita QUALQUER coluna como filtro — as colunas da tabela
        # são o vocabulário de parâmetros, e é o que o `definitions` lista.
        for tabela, definicao in (spec.get("definitions") or {}).items():
            props = (definicao or {}).get("properties") or {}
            rotas[str(tabela).strip("/")] = set(props)
        return rotas

    for caminho, operacoes in (spec.get("paths") or {}).items():
        if not isinstance(operacoes, dict):
            continue
        params: set[str] = set()
        # parâmetros declarados no caminho valem para todos os métodos
        for lista in (operacoes.get("parameters"), (operacoes.get("get") or {}).get("parameters")):
            for p in lista or []:
                if isinstance(p, dict) and p.get("in") == "query" and p.get("name"):
                    params.add(str(p["name"]))
        if "get" in operacoes:
            rotas[str(caminho).strip("/")] = params
    return rotas


def escolher_rota(
    spec: dict, palavras: tuple[str, ...], chaves: tuple[str, ...]
) -> Rota | None:
    """Melhor (endpoint, chave) do spec: nome casa o assunto E aceita a chave.

    Sem chave aceita não há escolha — devolver "a rota do assunto" sem filtro
    seria pior que não achar: traria o país inteiro.
    """
    rotas = rotas_do_spec(spec)
    postgrest = _e_postgrest(spec)

    melhor: tuple[tuple[int, int, int], Rota] | None = None
    for endpoint, params in rotas.items():
        nome = _norm(endpoint)
        acertos = sum(1 for p in palavras if _norm(p) in nome)
        if not acertos:
            continue
        # a chave mais específica que a rota aceita (a ordem de `chaves` é a
        # ordem de especificidade decidida por quem chama)
        posicao = next((i for i, c in enumerate(chaves) if c in params), None)
        if posicao is None:
            continue
        # ordena por: mais palavras casadas · chave mais específica · nome curto
        score = (-acertos, posicao, len(endpoint))
        if melhor is None or score < melhor[0]:
            melhor = (
                score,
                Rota(
                    endpoint=endpoint,
                    chave=chaves[posicao],
                    postgrest=postgrest,
                    param_pagina=next((p for p in PAGINA_OPENAPI if p in params), None),
                    param_tamanho=next((p for p in TAMANHO_OPENAPI if p in params), None),
                ),
            )
    return melhor[1] if melhor else None


async def descobrir(
    base_url: str, palavras: tuple[str, ...], chaves: tuple[str, ...]
) -> Rota | None:
    """`escolher_rota` sobre o spec do módulo, cacheado por (base, assunto)."""
    cache_key = (base_url, palavras, chaves)
    if cache_key in _rota_cache:
        return _rota_cache[cache_key]

    spec = await carregar_spec(base_url)
    rota = escolher_rota(spec, palavras, chaves) if spec else None
    # só cacheia acerto: spec indisponível hoje pode responder no próximo sync
    if rota is not None:
        _rota_cache[cache_key] = rota
    return rota
