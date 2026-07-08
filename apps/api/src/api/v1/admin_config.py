"""Painel de configuração (admin): plugar credenciais/URLs dos providers via API.

Só admin (is_superuser). Segredos são cifrados em repouso e retornados mascarados.
As chaves são restritas ao catálogo conhecido (services/config.CATALOGO).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.config import ConfigItem, ConfigSet
from ...services import config as service
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
