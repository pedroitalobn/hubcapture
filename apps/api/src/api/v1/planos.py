"""Endpoints de planos. Listagem pública; criação/edição só admin (is_superuser)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.planos import PlanoCreate, PlanoRead, PlanoUpdate
from ...services import planos as service
from ..deps import get_platform_db

router = APIRouter(tags=["planos"])


@router.get("/plans", response_model=list[PlanoRead])
async def listar_planos(
    session: AsyncSession = Depends(get_platform_db),
) -> list[PlanoRead]:
    rows = await service.listar(session, apenas_ativos=True)
    return [PlanoRead.model_validate(r) for r in rows]


@router.post("/plans", response_model=PlanoRead, status_code=status.HTTP_201_CREATED)
async def criar_plano(
    body: PlanoCreate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> PlanoRead:
    plano = await service.criar(session, body)
    return PlanoRead.model_validate(plano)


@router.patch("/plans/{plano_id}", response_model=PlanoRead)
async def atualizar_plano(
    plano_id: uuid.UUID,
    body: PlanoUpdate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> PlanoRead:
    plano = await service.obter(session, plano_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PLANO_NAO_ENCONTRADO")
    plano = await service.atualizar(session, plano, body)
    return PlanoRead.model_validate(plano)
