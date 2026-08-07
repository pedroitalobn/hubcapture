"""Endpoints de propostas (cache-first, RLS).

Os filtros aqui espelham a tela de captação: busca livre (programa/órgão/
código), natureza jurídica elegível, modalidade, órgão, qualificação, ano,
tipo (cadastrada × disponível), faixa de valor e ordenação. As opções dos
dropdowns vêm de `/proposals/facets` (só o que existe no território), o
consolidado de `/proposals/summary` e o "baixar relatório" de
`/proposals/report.csv`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.proposta import (
    PropostaPrazo,
    PropostaRead,
    PropostasFacetas,
    PropostasPagina,
    ResumoCaptacao,
)
from ...services import municipios as municipios_service
from ...services import pdf as pdf_service
from ...services import propostas as propostas_service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin (captação): desativado → eixo responde 404.
router = APIRouter(
    tags=["propostas"], dependencies=[Depends(require_modulo("captacao"))]
)


class FiltrosProposta(BaseModel):
    """Filtros da captação — compartilhados por lista, facetas, resumo e relatório."""

    # Multi-seleção: o painel recorta o território para os municípios que o
    # usuário quer ver agora (`?municipio=2611606&municipio=3550308`). Um valor
    # só continua valendo — vira uma lista de um item.
    municipio: list[str] | None = Field(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    )
    uf: str | None = Field(
        default=None, min_length=2, max_length=2, description="unidade federativa"
    )
    fonte: str | None = None
    area: str | None = Field(default=None, description="área de interesse (saude, educacao…)")
    situacao: str | None = None
    modalidade: str | None = Field(default=None, description="tipo de instrumento")
    orgao: str | None = Field(default=None, description="órgão/ministério concedente")
    natureza_juridica: str | None = Field(
        default=None, description="municipal | estadual_df | consorcio | empresa_publica | osc"
    )
    qualificacao: str | None = Field(default=None, description="tipo de transferência")
    categoria: str | None = Field(
        default=None, description="pílula de categoria (saude, infraestrutura, cultura…)"
    )
    ano: str | None = Field(default=None, max_length=4)
    mes: str | None = Field(
        default=None,
        pattern="^(0[1-9]|1[0-2])$",
        description="mês do prazo final (ou da atualização na fonte)",
    )
    q: str | None = Field(default=None, description="busca por programa, órgão ou código")
    valor_min: Decimal | None = Field(default=None, ge=0)
    valor_max: Decimal | None = Field(default=None, ge=0)
    tipo: str | None = Field(default=None, pattern="^(cadastrada|disponivel)$")


class FiltrosListagem(FiltrosProposta):
    ordenar: str | None = Field(
        default=None,
        pattern="^(recentes|prazo|prazo_distante|nome|orgao|valor)$",
        description="mais recentes · prazo (próximo/distante) · nome A-Z · órgão A-Z · valor",
    )


class FiltrosPagina(FiltrosListagem):
    """Só a listagem pagina — facetas, resumo e relatório enxergam o recorte todo."""

    limite: int | None = Field(
        default=None, ge=1, le=200, description="itens por página (sem limite: tudo)"
    )
    offset: int = Field(default=0, ge=0, description="itens já carregados")


@router.get("/proposals", response_model=PropostasPagina)
async def listar_propostas(
    filtros: Annotated[FiltrosPagina, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> PropostasPagina:
    """Página da listagem lida do banco (cache-first) + total do recorte."""
    rows, total = await propostas_service.listar_pagina(session, **filtros.model_dump())
    return PropostasPagina(
        # o nome do município lidera a exibição — completa o que a fonte não trouxe
        itens=await municipios_service.enriquecer(
            session, [PropostaRead.model_validate(r) for r in rows]
        ),
        total=total,
        limite=filtros.limite,
        offset=filtros.offset,
    )


@router.get("/proposals/facets", response_model=PropostasFacetas)
async def facetas_propostas(
    filtros: Annotated[FiltrosProposta, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> PropostasFacetas:
    """Opções de cada filtro com contagem — alimenta os dropdowns da tela."""
    dados = await propostas_service.facetas(session, **filtros.model_dump())
    return PropostasFacetas.model_validate(dados)


@router.get("/proposals/summary", response_model=ResumoCaptacao)
async def resumo_propostas(
    filtros: Annotated[FiltrosProposta, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> ResumoCaptacao:
    """Resumo consolidado: cards financeiros, série por ano, pipeline e vigentes."""
    dados = await propostas_service.resumo(session, **filtros.model_dump())
    return ResumoCaptacao.model_validate(dados)


@router.get("/proposals/report.csv")
async def relatorio_propostas(
    filtros: Annotated[FiltrosListagem, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    """Baixar relatório: o mesmo recorte da tela, em CSV (';', abre no Excel)."""
    rows = await propostas_service.listar(session, **filtros.model_dump())
    conteudo = propostas_service.gerar_csv(rows)
    return Response(
        content=conteudo.encode("utf-8-sig"),  # BOM: acento correto no Excel
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="captacao.csv"'},
    )


@router.get("/proposals/deadlines", response_model=list[PropostaPrazo])
async def propostas_por_prazo(
    dias: int = Query(default=30, ge=1, le=365),
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaPrazo]:
    """Propostas com prazo vencendo na janela — 'quais vencem este mês?'."""
    rows = await propostas_service.listar_por_prazo(session, dias=dias, municipio=municipio)
    mapa = await municipios_service.mapa_territorio(session)
    return [
        PropostaPrazo(
            proposta=(
                await municipios_service.enriquecer(
                    session, [PropostaRead.model_validate(p)], mapa=mapa
                )
            )[0],
            prazos_na_janela=prazos,
        )
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
    enriquecidas = await municipios_service.enriquecer(
        session, [PropostaRead.model_validate(row)]
    )
    return enriquecidas[0]


@router.get("/proposals/{proposta_id}/pdf")
async def exportar_pdf(
    proposta_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    row = await propostas_service.obter(session, proposta_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PROPOSTA_NAO_ENCONTRADA")
    mapa = await municipios_service.mapa_territorio(session)
    nome, uf = mapa.get(row.municipio_ibge or "", (None, None))
    conteudo = pdf_service.gerar_pdf_proposta(
        row, municipio_nome=row.municipio_nome or nome, uf=row.uf or uf
    )
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="proposta-{row.id_externo}.pdf"'},
    )
