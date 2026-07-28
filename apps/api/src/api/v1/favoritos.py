"""Endpoints de favoritos (RLS por usuario_id)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.curadoria import FavoritoCreate, FavoritoRead
from ...services import favoritos as service
from ..deps import get_rls_db

router = APIRouter(tags=["favoritos"])


@router.get("/favorites", response_model=list[FavoritoRead])
async def listar_favoritos(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[FavoritoRead]:
    rows = await service.listar(session, user.id)
    return [FavoritoRead.model_validate(r) for r in rows]


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
async def adicionar_favorito(
    body: FavoritoCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    await service.adicionar(session, user.id, body.proposta_id)
    return {"ok": True}


@router.delete("/favorites/{proposta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_favorito(
    proposta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.remover(session, user.id, proposta_id)
