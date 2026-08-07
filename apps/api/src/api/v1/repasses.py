"""Endpoints de repasses recebidos (cache-first, RLS) + Visão Geral consolidada."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors._http import ConnectorClientError
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.repasse import RepasseRead, ResumoEmendas, VisaoGeral
from ...services import fontes as fontes_service
from ...services import municipios as municipios_service
from ...services import repasses as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin (recebidos): desativado → eixo responde 404.
router = APIRouter(tags=["repasses"], dependencies=[Depends(require_modulo("recebidos"))])

# recorte da v1 (services/fontes.py): recebidos vêm do FNS
FONTES_PADRAO = list(fontes_service.RECEBIDOS)


class SyncRepassesRequest(BaseModel):
    municipio_ibge: str = Field(min_length=7, max_length=7)
    fontes: list[str] | None = None


class FiltrosEmendas(BaseModel):
    """Filtros da tela de emendas (modalidade, ano, parlamentar, órgão)."""

    municipio: list[str] | None = Field(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    )
    inicio: date | None = None
    fim: date | None = None
    ano: str | None = Field(default=None, max_length=4)
    modalidade: str | None = Field(default=None, description="individual | bancada | comissão")
    parlamentar: str | None = None
    orgao: str | None = None
    q: str | None = Field(default=None, description="busca por objeto, área, órgão ou código")


@router.get("/transfers", response_model=list[RepasseRead])
async def listar_repasses(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    fonte: str | None = Query(default=None),
    inicio: date | None = Query(default=None),
    fim: date | None = Query(default=None),
    emenda: bool | None = Query(default=None, description="só repasses de emenda"),
    orgao: str | None = Query(default=None),
    categoria: str | None = Query(default=None, description="área/função orçamentária"),
    q: str | None = Query(default=None, description="busca textual"),
    session: AsyncSession = Depends(get_rls_db),
) -> list[RepasseRead]:
    rows = await service.listar(
        session,
        municipio=municipio,
        fonte=fonte,
        inicio=inicio,
        fim=fim,
        emenda=emenda,
        orgao=orgao,
        categoria=categoria,
        q=q,
    )
    return await municipios_service.enriquecer(
        session, [RepasseRead.model_validate(r) for r in rows]
    )


@router.get("/transfers/amendments/summary", response_model=ResumoEmendas)
async def resumo_emendas(
    filtros: Annotated[FiltrosEmendas, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> ResumoEmendas:
    """Painel de emendas: cards empenhado/pago, evolução anual, distribuição por
    modalidade e por área, ranking de parlamentares e a lista detalhada."""
    return await service.resumo_emendas(session, **filtros.model_dump())


@router.get("/transfers/amendments/report.csv")
async def relatorio_emendas(
    filtros: Annotated[FiltrosEmendas, Query()],
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    """Exporta a lista de emendas filtrada (CSV ';', abre no Excel)."""
    rows = await service.listar_emendas(session, **filtros.model_dump())
    return Response(
        content=service.gerar_csv_emendas(rows).encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="emendas.csv"'},
    )


@router.get("/transfers/overview", response_model=VisaoGeral)
async def visao_geral(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    inicio: date | None = Query(default=None),
    fim: date | None = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
) -> VisaoGeral:
    return await service.visao_geral(session, municipio=municipio, inicio=inicio, fim=fim)


@router.post("/transfers/sync", response_model=dict)
async def sync_repasses(
    body: SyncRepassesRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    fontes = body.fontes or FONTES_PADRAO
    try:
        total = await service.sync_municipio(
            session,
            usuario_id=user.id,
            municipio_ibge=body.municipio_ibge,
            fontes=fontes,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="FONTE_DESCONHECIDA"
        ) from exc
    except ConnectorClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # fonte instável/indisponível
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FONTE_INDISPONIVEL: {type(exc).__name__}",
        ) from exc
    return {"gravados": total, "fontes": fontes}
