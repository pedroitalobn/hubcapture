"""Painel admin da assessoria: contatos de WhatsApp e a FILA de demandas.

A fila usa a sessão de PLATAFORMA de propósito: a demanda é do tenant que a
abriu (RLS por `usuario_id`), e quem responde é a administração — que precisa
ver todas. Sem isto a fila viria vazia, porque a sessão admin não tem tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.usuario import Usuario
from ...schemas.assessoria import AssessoriaContatosSet, ContatoAssessoriaRead
from ...schemas.demanda import DemandaComentario, DemandaFilaRead
from ...services import assessoria as service
from ...services import demandas as demandas_service
from ..deps import get_plataforma_db, get_platform_db

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


# ── Fila de demandas (ponto 20) ───────────────────────────────────────────


@router.get("/admin/advisory/requests", response_model=list[DemandaFilaRead])
async def listar_fila(
    situacao: str | None = Query(
        default=None, description="aberta|em_andamento|resolvida|cancelada"
    ),
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_plataforma_db),
) -> list[DemandaFilaRead]:
    try:
        linhas = await demandas_service.listar_fila(session, situacao=situacao)
    except demandas_service.SituacaoInvalida:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SITUACAO_INVALIDA"
        ) from None
    return [
        DemandaFilaRead(
            **DemandaFilaRead.model_validate(d).model_dump(
                exclude={"usuario_email", "usuario_nome"}
            ),
            usuario_email=u.email if u else None,
            usuario_nome=u.nome if u else None,
        )
        for d, u in linhas
    ]


@router.post("/admin/advisory/requests/{demanda_id}/reply", response_model=DemandaFilaRead)
async def responder_demanda(
    demanda_id: uuid.UUID,
    body: DemandaComentario,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_plataforma_db),
) -> DemandaFilaRead:
    """Resposta da assessoria — entra no histórico e pode mudar a situação."""
    try:
        demanda = await demandas_service.responder(
            session, demanda_id, texto=body.texto, situacao=body.situacao
        )
    except demandas_service.DemandaNaoEncontrada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DEMANDA_NAO_ENCONTRADA"
        ) from None
    except demandas_service.SituacaoInvalida:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SITUACAO_INVALIDA"
        ) from None
    return DemandaFilaRead.model_validate(demanda)
