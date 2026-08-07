"""Endpoints de parecer — consulta pelo número do PLANO DE TRABALHO.

Rotas em inglês (§25): pareceres → opinions, plano de trabalho → work-plan.
Fica sob o módulo `captacao` (§29): eixo desligado → 404 no eixo inteiro.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.parecer import ParecerPagina
from ...services import pareceres as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

router = APIRouter(tags=["pareceres"], dependencies=[Depends(require_modulo("captacao"))])


@router.get("/opinions", response_model=ParecerPagina)
async def pareceres_por_plano(
    work_plan: str = Query(
        ..., min_length=1, description="número do plano de trabalho (ex.: 14275/2026)"
    ),
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> ParecerPagina:
    """Pareceres de um plano de trabalho — a consulta direta, sem passar pela proposta."""
    itens, coleta = await service.por_plano(
        session, work_plan, atualizar=atualizar, usuario_id=usuario.id
    )
    return ParecerPagina(itens=itens, coleta=coleta)


@router.get("/proposals/{proposta_id}/opinions", response_model=ParecerPagina)
async def pareceres_da_proposta(
    proposta_id: uuid.UUID,
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> ParecerPagina:
    """Pareceres do plano de trabalho vinculado à proposta."""
    itens, coleta = await service.por_proposta(
        session, proposta_id, atualizar=atualizar, usuario_id=usuario.id
    )
    return ParecerPagina(itens=itens, coleta=coleta)
