"""Endpoints de monitoramentos (RLS por usuario_id).

Dois sabores: proposta-chave (mudança de status/prazo) e BUSCA (futuras
propostas de um município/área — o "monitorar o que ainda vai aparecer").
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.monitoramento import (
    MonitoramentoBuscaCreate,
    MonitoramentoBuscaRead,
    MonitoramentoCreate,
    MonitoramentoRead,
)
from ...services import monitoramentos as service
from ..deps import get_rls_db

router = APIRouter(tags=["monitoramentos"])


@router.get("/monitors/searches", response_model=list[MonitoramentoBuscaRead])
async def listar_buscas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[MonitoramentoBuscaRead]:
    rows = await service.listar_buscas(session, user.id)
    return [MonitoramentoBuscaRead.model_validate(r) for r in rows]


@router.post(
    "/monitors/searches",
    response_model=MonitoramentoBuscaRead,
    status_code=status.HTTP_201_CREATED,
)
async def criar_busca(
    body: MonitoramentoBuscaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> MonitoramentoBuscaRead:
    busca = await service.criar_busca(
        session,
        user.id,
        municipio_ibge=body.municipio_ibge,
        area=body.area,
        fonte=body.fonte,
        canais=body.canais,
    )
    return MonitoramentoBuscaRead.model_validate(busca)


@router.delete("/monitors/searches/{busca_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_busca(
    busca_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.desativar_busca(session, user.id, busca_id)


@router.get("/monitors", response_model=list[MonitoramentoRead])
async def listar_monitoramentos(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[MonitoramentoRead]:
    rows = await service.listar(session, user.id)
    return [MonitoramentoRead.model_validate(r) for r in rows]


@router.post(
    "/monitors", response_model=MonitoramentoRead, status_code=status.HTTP_201_CREATED
)
async def criar_monitoramento(
    body: MonitoramentoCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> MonitoramentoRead:
    mon = await service.criar(session, user.id, body.proposta_id, body.canais)
    return MonitoramentoRead.model_validate(mon)


@router.delete("/monitors/{monitoramento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_monitoramento(
    monitoramento_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.desativar(session, user.id, monitoramento_id)
