"""Endpoints de administração (is_superuser): usuários, convites, atribuição de plano.

Criação de usuário (admin e via convite) passa pelo UserManager (hash de senha).
`aceitar-convite` é público (o convidado ainda não tem conta).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import UserManager, current_superuser, get_user_manager
from ...models.base_conhecimento import BaseConhecimento
from ...models.usuario import Usuario
from ...schemas.config import ConhecimentoCreate
from ...schemas.planos import (
    AceitarConvite,
    AdminUsuarioCreate,
    AdminUsuarioRead,
    AdminUsuarioUpdate,
    AtribuirPlano,
    ConviteCreate,
    ConviteRead,
)
from ...schemas.user import UserRead
from ...services import gestao_usuarios as service
from ..deps import get_platform_db

router = APIRouter(tags=["admin"])


@router.post("/admin/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def admin_criar_usuario(
    body: AdminUsuarioCreate,
    _admin: Usuario = Depends(current_superuser),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_platform_db),
) -> Usuario:
    return await service.criar_usuario(session, user_manager, body)


@router.get("/admin/users", response_model=list[AdminUsuarioRead])
async def admin_listar_usuarios(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[Usuario]:
    return await service.listar_usuarios(session)


@router.patch("/admin/users/{usuario_id}", response_model=AdminUsuarioRead)
async def admin_atualizar_usuario(
    usuario_id: uuid.UUID,
    body: AdminUsuarioUpdate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> Usuario:
    return await service.atualizar_usuario(session, usuario_id, body)


@router.patch("/admin/users/{usuario_id}/plan", status_code=status.HTTP_204_NO_CONTENT)
async def admin_atribuir_plano(
    usuario_id: uuid.UUID,
    body: AtribuirPlano,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    await service.atribuir_plano(session, usuario_id, body.plano_id)


@router.post("/admin/invites", response_model=ConviteRead, status_code=status.HTTP_201_CREATED)
async def admin_criar_convite(
    body: ConviteCreate,
    admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> ConviteRead:
    convite = await service.criar_convite(session, body, convidado_por=admin.id)
    return ConviteRead.model_validate(convite)


@router.get("/admin/invites", response_model=list[ConviteRead])
async def admin_listar_convites(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ConviteRead]:
    rows = await service.listar_convites(session)
    return [ConviteRead.model_validate(r) for r in rows]


@router.post("/auth/accept-invite", response_model=UserRead)
async def aceitar_convite(
    body: AceitarConvite,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_platform_db),
) -> Usuario:
    return await service.aceitar_convite(session, user_manager, body)


@router.post("/admin/knowledge", status_code=status.HTTP_201_CREATED)
async def admin_add_conhecimento(
    body: ConhecimentoCreate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Adiciona material à base de conhecimento do Copiloto."""
    session.add(
        BaseConhecimento(
            titulo=body.titulo,
            conteudo=body.conteudo,
            categoria=body.categoria,
            tags=body.tags,
        )
    )
    return {"ok": True}
