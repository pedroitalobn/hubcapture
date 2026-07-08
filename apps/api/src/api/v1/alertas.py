"""Endpoints de alertas (RLS por usuario_id)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.monitoramento import AlertaRead
from ...services import alertas as service
from ..deps import get_rls_db

router = APIRouter(tags=["alertas"])


@router.get("/alertas", response_model=list[AlertaRead])
async def listar_alertas(
    nao_lidos: bool = Query(default=False),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[AlertaRead]:
    rows = await service.listar(session, user.id, apenas_nao_lidos=nao_lidos)
    return [AlertaRead.model_validate(r) for r in rows]


@router.post("/alertas/{alerta_id}/lido", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_lido(
    alerta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.marcar_lido(session, user.id, alerta_id)
