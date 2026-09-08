"""Consultas de propostas salvas — o CRUD das abas do construtor (§61).

Todo o router está atrás do módulo `captacao`: a aba é exploração (montar
recorte), não leitura do painel — desligar a captação tira o construtor, não o
Meu painel (§40).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.consultas import (
    ConsultaCreate,
    ConsultaRead,
    ConsultasOrdem,
    ConsultaUpdate,
)
from ...services import consultas_propostas as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

router = APIRouter(tags=["consultas"], dependencies=[Depends(require_modulo("captacao"))])


async def _obter_ou_404(session, user, consulta_id) -> object:
    consulta = await service.obter(session, user.id, consulta_id)
    if consulta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONSULTA_NAO_ENCONTRADA")
    return consulta


@router.get("/proposals/views", response_model=list[ConsultaRead])
async def listar_consultas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[ConsultaRead]:
    """As abas do gestor. Sem nenhuma, devolve a inicial já criada."""
    rows = await service.garantir_padrao(session, user.id)
    return [ConsultaRead.model_validate(r) for r in rows]


@router.post("/proposals/views", response_model=ConsultaRead, status_code=status.HTTP_201_CREATED)
async def criar_consulta(
    body: ConsultaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> ConsultaRead:
    try:
        consulta = await service.criar(session, user.id, body)
    except service.LimiteConsultasExcedido:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"LIMITE_CONSULTAS: máximo de {service.MAX_CONSULTAS} abas",
        ) from None
    return ConsultaRead.model_validate(consulta)


@router.patch("/proposals/views/{consulta_id}", response_model=ConsultaRead)
async def atualizar_consulta(
    consulta_id: uuid.UUID,
    body: ConsultaUpdate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> ConsultaRead:
    consulta = await _obter_ou_404(session, user, consulta_id)
    consulta = await service.atualizar(session, consulta, body)
    return ConsultaRead.model_validate(consulta)


@router.delete("/proposals/views/{consulta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_consulta(
    consulta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    consulta = await _obter_ou_404(session, user, consulta_id)
    await service.remover(session, consulta)


@router.put("/proposals/views/order", response_model=list[ConsultaRead])
async def reordenar_consultas(
    body: ConsultasOrdem,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[ConsultaRead]:
    rows = await service.reordenar(session, user.id, body.ids)
    return [ConsultaRead.model_validate(r) for r in rows]
