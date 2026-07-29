"""Painel de configuração (admin): plugar credenciais/URLs dos providers via API.

Só admin (is_superuser). Segredos são cifrados em repouso e retornados mascarados.
As chaves são restritas ao catálogo conhecido (services/config.CATALOGO).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.config import (
    ConfigItem,
    ConfigSet,
    LlmChaveIn,
    LlmModelosOut,
    LlmProviderOut,
)
from ...services import config as service
from ...services import llm_providers
from ..deps import get_platform_db

router = APIRouter(tags=["admin-config"])


@router.get("/admin/config", response_model=list[ConfigItem])
async def listar_config(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ConfigItem]:
    itens = await service.listar_catalogo(session)
    return [ConfigItem(**i) for i in itens]


@router.put("/admin/config", response_model=list[ConfigItem])
async def definir_config(
    body: ConfigSet,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ConfigItem]:
    if not service.chave_valida(body.chave):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"CHAVE_DESCONHECIDA: {body.chave}")
    await service.definir(session, body.chave, body.valor)
    itens = await service.listar_catalogo(session)
    return [ConfigItem(**i) for i in itens]


@router.get("/admin/config/llm/providers", response_model=list[LlmProviderOut])
async def listar_llm_providers(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[LlmProviderOut]:
    """Provedores de LLM suportados, com status da chave e seleção de modelo atual."""
    modelo_chat = await service.get_valor(session, "llm_model_chat") or ""
    modelo_resumo = await service.get_valor(session, "llm_model_resumo") or ""
    saida: list[LlmProviderOut] = []
    for p in llm_providers.PROVIDERS:
        chave = llm_providers.chave_config(p.id)
        valor = await service.get_valor(session, chave)
        saida.append(
            LlmProviderOut(
                id=p.id,
                label=p.label,
                chave=chave,
                configurado=bool(valor),
                chave_mascarada=service.mascarar(valor) if valor else None,
                docs_url=p.docs_url,
                modelo_chat=modelo_chat.startswith(f"{p.id}/"),
                modelo_resumo=modelo_resumo.startswith(f"{p.id}/"),
            )
        )
    return saida


@router.put("/admin/config/llm/{provider_id}/chave", response_model=LlmModelosOut)
async def definir_llm_chave(
    provider_id: str,
    body: LlmChaveIn,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> LlmModelosOut:
    """Grava a API key do provedor e já devolve os modelos dele (menor fricção)."""
    if not llm_providers.provider_valido(provider_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"PROVIDER_DESCONHECIDO: {provider_id}")
    if not body.api_key.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "API_KEY_VAZIA")
    await service.definir(session, llm_providers.chave_config(provider_id), body.api_key.strip())
    return LlmModelosOut(**await llm_providers.listar_modelos(provider_id, body.api_key.strip()))


@router.get("/admin/config/llm/{provider_id}/modelos", response_model=LlmModelosOut)
async def listar_llm_modelos(
    provider_id: str,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> LlmModelosOut:
    """Modelos do provedor usando a chave já salva (listagem ao vivo + fallback)."""
    if not llm_providers.provider_valido(provider_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"PROVIDER_DESCONHECIDO: {provider_id}")
    api_key = await service.get_valor(session, llm_providers.chave_config(provider_id))
    if not api_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CHAVE_NAO_CONFIGURADA")
    return LlmModelosOut(**await llm_providers.listar_modelos(provider_id, api_key))
