"""Endpoints de monitoramentos (RLS por usuario_id)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.monitoramento import MonitoramentoCreate, MonitoramentoRead
from ...services import monitoramentos as service
from ..deps import get_rls_db

router = APIRouter(tags=["monitoramentos"])


@router.get("/monitoramentos", response_model=list[MonitoramentoRead])
async def listar_monitoramentos(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[MonitoramentoRead]:
    rows = await service.listar(session, user.id)
    return [MonitoramentoRead.model_validate(r) for r in rows]


@router.post(
    "/monitoramentos", response_model=MonitoramentoRead, status_code=status.HTTP_201_CREATED
)
async def criar_monitoramento(
    body: MonitoramentoCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> MonitoramentoRead:
    mon = await service.criar(session, user.id, body.proposta_id, body.canais)
    return MonitoramentoRead.model_validate(mon)
