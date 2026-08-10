"""Painel admin da assessoria: editar os contatos de WhatsApp em runtime."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.assessoria import AssessoriaContatosSet, ContatoAssessoriaRead
from ...services import assessoria as service
from ..deps import get_platform_db

router = APIRouter(tags=["admin-assessoria"])


@router.get("/admin/advisory/contacts", response_model=list[ContatoAssessoriaRead])
async def listar_contatos(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoAssessoriaRead]:
    return [ContatoAssessoriaRead(**c) for c in await service.listar(session)]


@router.put("/admin/advisory/contacts", response_model=list[ContatoAssessoriaRead])
async def definir_contatos(
    body: AssessoriaContatosSet,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoAssessoriaRead]:
    await service.definir(session, [c.model_dump() for c in body.contatos])
    return [ContatoAssessoriaRead(**c) for c in await service.listar(session)]
