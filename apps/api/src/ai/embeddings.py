"""Embeddings (LiteLLM) — geração de vetores para RAG.

Provider/model/chave vêm do painel admin (config runtime). Desabilitado sem
`embedding_api_key` (retorna None) — o RAG então cai para busca textual.
Dimensão deve casar com `proposta_embeddings.embedding` (1536).
"""

from __future__ import annotations

from ..services import config as config_service

DIM = 1536


async def embed(textos: list[str]) -> list[list[float]] | None:
    """Retorna os vetores dos textos, ou None se embeddings está desabilitado."""
    if not textos:
        return []
    api_key = await config_service.resolver("embedding_api_key")
    if not api_key:
        return None
    modelo = await config_service.resolver("embedding_model") or "text-embedding-3-small"
    try:
        import litellm
    except ImportError:
        return None
    resp = await litellm.aembedding(model=modelo, input=textos, api_key=api_key)
    return [item["embedding"] for item in resp["data"]]


async def embed_um(texto: str) -> list[float] | None:
    vetores = await embed([texto])
    return vetores[0] if vetores else None
