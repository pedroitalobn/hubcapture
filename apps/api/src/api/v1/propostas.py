"""Endpoints de propostas (cache-first, RLS)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.proposta import AnoResumo, PropostaRead
from ...services import pdf as pdf_service
from ...services import propostas as propostas_service
from ..deps import get_rls_db

router = APIRouter(tags=["propostas"])


@router.get("/propostas", response_model=list[PropostaRead])
async def listar_propostas(
    municipio: str | None = Query(default=None, description="código IBGE (7 dígitos)"),
    fonte: str | None = Query(default=None),
    area: str | None = Query(default=None, description="reservado (áreas) — futuro"),
    situacao: str | None = Query(default=None),
    ano: int | None = Query(default=None, description="ano de CRIAÇÃO da proposta"),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaRead]:
    rows = await propostas_service.listar(
        session, municipio=municipio, fonte=fonte, situacao=situacao, ano=ano
    )
    return [PropostaRead.model_validate(r) for r in rows]


# precede /propostas/{proposta_id} (senão 'anos' cairia na rota de UUID)
@router.get("/propostas/anos", response_model=list[AnoResumo])
async def listar_anos(
    municipio: str | None = Query(default=None, description="código IBGE (7 dígitos)"),
    fonte: str | None = Query(default=None),
    situacao: str | None = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
) -> list[AnoResumo]:
    """Safras por ano de criação (para as abas/chips de ano no painel)."""
    return await propostas_service.anos(
        session, municipio=municipio, fonte=fonte, situacao=situacao
    )


@router.get("/propostas/{proposta_id}", response_model=PropostaRead)
async def obter_proposta(
    proposta_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> PropostaRead:
    row = await propostas_service.obter(session, proposta_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PROPOSTA_NAO_ENCONTRADA")
    return PropostaRead.model_validate(row)


@router.get("/propostas/{proposta_id}/pdf")
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
