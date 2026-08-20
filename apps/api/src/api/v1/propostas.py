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

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.proposta import (
    PropostaPrazo,
    PropostaRead,
    PropostasFacetas,
    PropostasPagina,
    ResumoCaptacao,
)
from ...services import municipios as municipios_service
from ...services import pdf as pdf_service
from ...services import plano_gates
from ...services import propostas as propostas_service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# O módulo "captação" cobre a EXPLORAÇÃO ativa — filtros específicos (lista/
# facetas/relatório) e a consulta ao vivo às fontes (live-search, em
# consulta_avulsa.py). As leituras de CACHE do território (resumo, prazos,
# detalhe e espelho PDF) pertencem ao Meu painel e ficam FORA do gate:
# desativar a captação não pode apagar o dashboard (§40).
router = APIRouter(tags=["propostas"])
_gate_captacao = [Depends(require_modulo("captacao"))]


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
    # Recorte de fonte: irmão do de município — o trilho lateral escolhe QUAIS
    # das fontes do perfil entram no painel agora, e vale para todas as lentes.
    fonte: list[str] | None = Field(
        default=None,
        description="grupo de fonte ('transferegov', 'fns') ou connector id — repita para várias",
    )
    area: str | None = Field(default=None, description="área de interesse (saude, educacao…)")
    situacao: str | None = None
    modalidade: str | None = Field(default=None, description="tipo de instrumento")
    orgao: str | None = Field(default=None, description="órgão/ministério concedente")
    natureza_juridica: str | None = Field(
        default=None, description="municipal | estadual_df | consorcio | empresa_publica | osc"
    )
    # lente de consulta (duas vias) sobre a natureza acima: quem propõe é o
    # município ou é outro. Cobre a base inteira — ver `grupo_natureza_de`.
    natureza_grupo: str | None = Field(
        default=None,
        pattern="^(entes_municipais|outros)$",
        description="lente da natureza jurídica: entes_municipais | outros",
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


@router.get("/proposals", response_model=PropostasPagina, dependencies=_gate_captacao)
async def listar_propostas(
    filtros: Annotated[FiltrosPagina, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> PropostasPagina:
    """Página da listagem lida do banco (cache-first) + total do recorte."""
    dados = filtros.model_dump()
    rows, total = await propostas_service.listar_pagina(session, **dados)
    return PropostasPagina(
        # o nome do município lidera a exibição — completa o que a fonte não trouxe
        itens=await municipios_service.enriquecer(
            session, [PropostaRead.model_validate(r) for r in rows]
        ),
        total=total,
        limite=filtros.limite,
        offset=filtros.offset,
        atualizado_em=await propostas_service.atualizado_em(session, **dados),
    )


@router.get("/proposals/facets", response_model=PropostasFacetas, dependencies=_gate_captacao)
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


@router.get("/proposals/report.csv", dependencies=_gate_captacao)
async def relatorio_propostas(
    filtros: Annotated[FiltrosListagem, Query()],
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    """Baixar relatório: o mesmo recorte da tela, em CSV (';', abre no Excel)."""
    await plano_gates.exigir_feature(session, user, "relatorio_csv")
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
    enriquecidas = await municipios_service.enriquecer(session, [PropostaRead.model_validate(row)])
    return enriquecidas[0]


@router.get("/proposals/{proposta_id}/pdf")
async def exportar_pdf(
    proposta_id: uuid.UUID,
    inline: bool = Query(
        default=False,
        description="abrir no visualizador em vez de baixar (pré-visualização)",
    ),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    """Espelho da proposta em PDF — a peça que o gestor encaminha a quem decide."""
    await plano_gates.exigir_feature(session, user, "export_pdf")
    row = await propostas_service.obter(session, proposta_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PROPOSTA_NAO_ENCONTRADA")
    # O espelho abre pelo município (§35) — se o cache não tem o nome, resolve
    # pelo território do usuário. `expunge` desliga a linha da sessão: o
    # preenchimento é só para o documento, não vira UPDATE.
    mapa = await municipios_service.mapa_territorio(session)
    nome_municipio, uf_municipio = mapa.get(row.municipio_ibge or "", (None, None))
    session.expunge(row)
    row.municipio_nome = row.municipio_nome or nome_municipio
    row.uf = row.uf or uf_municipio or municipios_service.uf_do_ibge(row.municipio_ibge)

    conteudo = pdf_service.gerar_pdf_proposta(row)
    nome = pdf_service.nome_arquivo(row)
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{nome}"',
            # o espelho carrega a data de emissão impressa: cachear serviria PDF
            # velho como se fosse o estado de hoje
            "Cache-Control": "no-store",
        },
    )
