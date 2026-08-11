"""Endpoints de propostas (cache-first, RLS)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.proposta import FiltrosPropostas, PropostaRead
from ...services import pdf as pdf_service
from ...services import propostas as propostas_service
from ..deps import get_rls_db

router = APIRouter(tags=["propostas"])


@router.get("/propostas", response_model=list[PropostaRead])
async def listar_propostas(
    numero: str | None = Query(
        default=None,
        description="busca por número da proposta / id externo / emenda (contém)",
    ),
    municipio: list[str] | None = Query(
        default=None, description="código(s) IBGE (7 dígitos) — repetir p/ vários"
    ),
    fonte: str | None = Query(default=None),
    area: str | None = Query(default=None, description="reservado (áreas) — futuro"),
    situacao: str | None = Query(default=None),
    natureza_juridica: list[str] | None = Query(
        default=None, description="slug(s) de natureza jurídica do proponente"
    ),
    valor_min: Decimal | None = Query(default=None, ge=0, description="valor total ≥"),
    valor_max: Decimal | None = Query(default=None, ge=0, description="valor total ≤"),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaRead]:
    if valor_min is not None and valor_max is not None and valor_min > valor_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RANGE_VALOR_INVALIDO",
        )
    rows = await propostas_service.listar(
        session,
        numero=numero,
        municipios=municipio,
        fonte=fonte,
        situacao=situacao,
        naturezas_juridicas=natureza_juridica,
        valor_min=valor_min,
        valor_max=valor_max,
    )
    return [PropostaRead.model_validate(r) for r in rows]


# precisa vir ANTES de /propostas/{proposta_id} (senão "filtros" cai no UUID)
@router.get("/propostas/filtros", response_model=FiltrosPropostas)
async def opcoes_de_filtro(
    session: AsyncSession = Depends(get_rls_db),
) -> FiltrosPropostas:
    return await propostas_service.filtros(session)


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
