"""Endpoints de propostas (cache-first, RLS)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.proposta import PropostaPrazo, PropostaRead
from ...services import pdf as pdf_service
from ...services import propostas as propostas_service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin (captação): desativado → eixo responde 404.
router = APIRouter(
    tags=["propostas"], dependencies=[Depends(require_modulo("captacao"))]
)


@router.get("/proposals", response_model=list[PropostaRead])
async def listar_propostas(
    municipio: str | None = Query(default=None, description="código IBGE (7 dígitos)"),
    fonte: str | None = Query(default=None),
    area: str | None = Query(default=None, description="área de interesse (saude, educacao…)"),
    situacao: str | None = Query(default=None),
    valor_min: Decimal | None = Query(default=None, ge=0),
    valor_max: Decimal | None = Query(default=None, ge=0),
    tipo: str | None = Query(default=None, pattern="^(cadastrada|disponivel)$"),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaRead]:
    rows = await propostas_service.listar(
        session,
        municipio=municipio,
        fonte=fonte,
        situacao=situacao,
        area=area,
        valor_min=valor_min,
        valor_max=valor_max,
        tipo=tipo,
    )
    return [PropostaRead.model_validate(r) for r in rows]


@router.get("/proposals/deadlines", response_model=list[PropostaPrazo])
async def propostas_por_prazo(
    dias: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaPrazo]:
    """Propostas com prazo vencendo na janela — 'quais vencem este mês?'."""
    rows = await propostas_service.listar_por_prazo(session, dias=dias)
    return [
        PropostaPrazo(proposta=PropostaRead.model_validate(p), prazos_na_janela=prazos)
        for p, prazos in rows
    ]


@router.get("/proposals/{proposta_id}", response_model=PropostaRead)
async def obter_proposta(
    proposta_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> PropostaRead:
    row = await propostas_service.obter(session, proposta_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PROPOSTA_NAO_ENCONTRADA")
    return PropostaRead.model_validate(row)


@router.get("/proposals/{proposta_id}/pdf")
async def exportar_pdf(
    proposta_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    row = await propostas_service.obter(session, proposta_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PROPOSTA_NAO_ENCONTRADA")
    conteudo = pdf_service.gerar_pdf_proposta(row)
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="proposta-{row.id_externo}.pdf"'},
    )
