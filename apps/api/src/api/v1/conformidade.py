"""Endpoints de conformidade fiscal (CAUC/CAPAG) — cache-first, RLS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors._http import ConnectorClientError
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.conformidade import ConformidadeResumo
from ...services import conformidade as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin: desativado → todo o eixo responde 404.
router = APIRouter(tags=["conformidade"], dependencies=[Depends(require_modulo("conformidade"))])


class SyncConformidadeRequest(BaseModel):
    municipio_ibge: str = Field(min_length=7, max_length=7)


@router.get("/compliance", response_model=ConformidadeResumo)
async def conformidade_resumo(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    session: AsyncSession = Depends(get_rls_db),
) -> ConformidadeResumo:
    return await service.resumo(session, municipio=municipio)


@router.post("/compliance/sync", response_model=dict)
async def conformidade_sync(
    body: SyncConformidadeRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    try:
        n = await service.sync_municipio(
            session, usuario_id=user.id, municipio_ibge=body.municipio_ibge
        )
    except ConnectorClientError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail=f"FONTE_INDISPONIVEL: {type(exc).__name__}"
        ) from exc
    return {"gravados": n}
