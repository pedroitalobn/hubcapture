"""Painel de módulos (admin): ativar/desativar eixos do produto em runtime.

Só admin (is_superuser). Desligar um módulo esconde a dimensão do perfil/menu
e faz os endpoints do eixo responderem 404 — sem redeploy.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.modulo import ModuloItem, ModuloSet
from ...services import modulos as service
from ..deps import get_platform_db

router = APIRouter(tags=["admin-modulos"])


@router.get("/admin/modulos", response_model=list[ModuloItem])
async def listar_modulos(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ModuloItem]:
    return [ModuloItem(**m) for m in await service.listar(session)]


@router.put("/admin/modulos", response_model=list[ModuloItem])
async def definir_modulo(
    body: ModuloSet,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ModuloItem]:
    if not service.modulo_valido(body.chave):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"MODULO_DESCONHECIDO: {body.chave}"
        )
    await service.definir(session, body.chave, body.ativo)
    return [ModuloItem(**m) for m in await service.listar(session)]
