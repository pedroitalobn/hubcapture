"""Assessoria orçamentária — falar com uma PESSOA e ABRIR uma demanda.

Duas metades: os contatos de WhatsApp (lista curada, editada no painel admin) e
a **central de demandas** (ponto 20 do feedback) — o pedido que fica registrado,
com estado e histórico, em vez de se perder na conversa. As duas vivem sob o
módulo `assessoria`, desligável pelo painel (§29).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.assessoria import ContatoAssessoriaRead
from ...schemas.demanda import DemandaComentario, DemandaCreate, DemandaRead
from ...services import assessoria as service
from ...services import demandas as demandas_service
from ...services.modulos import require_modulo
from ..deps import get_platform_db, get_rls_db

router = APIRouter(tags=["assessoria"], dependencies=[Depends(require_modulo("assessoria"))])


@router.get("/advisory/contacts", response_model=list[ContatoAssessoriaRead])
async def listar_contatos(
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoAssessoriaRead]:
    return [ContatoAssessoriaRead(**c) for c in await service.listar(session)]


# ── Central de demandas ────────────────────────────────────────────────────
# A demanda é do USUÁRIO (RLS por usuario_id), diferente dos contatos acima,
# que são lista de plataforma. Por isso estas rotas usam a sessão RLS.


@router.get("/advisory/requests", response_model=list[DemandaRead])
async def listar_demandas(
    situacao: str | None = Query(
        default=None, description="aberta|em_andamento|resolvida|cancelada"
    ),
    abertas: bool = Query(default=False, description="só o que ainda está em aberto"),
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[DemandaRead]:
    try:
        rows = await demandas_service.listar(
            session, situacao=situacao, incluir_resolvidas=not abertas
        )
    except demandas_service.SituacaoInvalida:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SITUACAO_INVALIDA"
        ) from None
    return [DemandaRead.model_validate(d) for d in rows]


@router.post(
    "/advisory/requests", response_model=DemandaRead, status_code=status.HTTP_201_CREATED
)
async def criar_demanda(
    body: DemandaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> DemandaRead:
    demanda = await demandas_service.criar(
        session,
        user.id,
        assunto=body.assunto,
        descricao=body.descricao,
        municipio_ibge=body.municipio_ibge,
        proposta_id=body.proposta_id,
    )
    return DemandaRead.model_validate(demanda)


@router.post("/advisory/requests/{demanda_id}/messages", response_model=DemandaRead)
async def comentar_demanda(
    demanda_id: uuid.UUID,
    body: DemandaComentario,
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> DemandaRead:
    """Mensagem do gestor na própria demanda (e, se ele quiser, encerramento)."""
    try:
        demanda = await demandas_service.comentar(
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
    return DemandaRead.model_validate(demanda)
