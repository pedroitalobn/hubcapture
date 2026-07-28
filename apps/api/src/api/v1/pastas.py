"""Endpoints de pastas e vínculo pasta↔proposta (RLS por usuario_id)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.curadoria import (
    PastaCreate,
    PastaPropostaCreate,
    PastaRead,
    PastaUpdate,
)
from ...services import pastas as service
from ..deps import get_rls_db

router = APIRouter(tags=["pastas"])


async def _get_pasta_ou_404(session, user, pasta_id):
    pasta = await service.obter(session, user.id, pasta_id)
    if pasta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PASTA_NAO_ENCONTRADA")
    return pasta


@router.get("/folders", response_model=list[PastaRead])
async def listar_pastas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PastaRead]:
    rows = await service.listar(session, user.id)
    return [PastaRead.model_validate(r) for r in rows]


@router.post("/folders", response_model=PastaRead, status_code=status.HTTP_201_CREATED)
async def criar_pasta(
    body: PastaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PastaRead:
    pasta = await service.criar(session, user.id, body)
    return PastaRead.model_validate(pasta)


@router.patch("/folders/{pasta_id}", response_model=PastaRead)
async def atualizar_pasta(
    pasta_id: uuid.UUID,
    body: PastaUpdate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PastaRead:
    pasta = await _get_pasta_ou_404(session, user, pasta_id)
    pasta = await service.atualizar(session, pasta, body)
    return PastaRead.model_validate(pasta)


@router.get("/folders/{pasta_id}/proposals", response_model=list[uuid.UUID])
async def listar_propostas_da_pasta(
    pasta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[uuid.UUID]:
    await _get_pasta_ou_404(session, user, pasta_id)
    return await service.propostas_da_pasta(session, pasta_id)


@router.post("/folders/{pasta_id}/proposals", status_code=status.HTTP_201_CREATED)
async def adicionar_proposta(
    pasta_id: uuid.UUID,
    body: PastaPropostaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    await _get_pasta_ou_404(session, user, pasta_id)
    await service.adicionar_proposta(session, pasta_id, body.proposta_id)
    return {"ok": True}


@router.delete(
    "/folders/{pasta_id}/proposals/{proposta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_proposta(
    pasta_id: uuid.UUID,
    proposta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await _get_pasta_ou_404(session, user, pasta_id)
    await service.remover_proposta(session, pasta_id, proposta_id)
