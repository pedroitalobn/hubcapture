"""Endpoints de repasses recebidos (cache-first, RLS) + Visão Geral consolidada."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors._http import ConnectorClientError
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.repasse import RepasseRead, VisaoGeral
from ...services import repasses as service
from ..deps import get_rls_db

router = APIRouter(tags=["repasses"])

FONTES_PADRAO = ["fpm", "emendas"]


class SyncRepassesRequest(BaseModel):
    municipio_ibge: str = Field(min_length=7, max_length=7)
    fontes: list[str] | None = None


@router.get("/transfers", response_model=list[RepasseRead])
async def listar_repasses(
    municipio: str | None = Query(default=None, description="código IBGE (7 dígitos)"),
    fonte: str | None = Query(default=None),
    inicio: date | None = Query(default=None),
    fim: date | None = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
) -> list[RepasseRead]:
    rows = await service.listar(
        session, municipio=municipio, fonte=fonte, inicio=inicio, fim=fim
    )
    return [RepasseRead.model_validate(r) for r in rows]


@router.get("/transfers/overview", response_model=VisaoGeral)
async def visao_geral(
    municipio: str | None = Query(default=None),
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except Exception as exc:  # fonte instável/indisponível
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FONTE_INDISPONIVEL: {type(exc).__name__}",
        ) from exc
    return {"gravados": total, "fontes": fontes}
