"""Endpoints de obras (execução — SISMOB/SIMEC/CAIXA) — cache-first, RLS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.obra import ObraRead, ObrasResumo
from ...services import municipios as municipios_service
from ...services import obras as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin: desativado → todo o eixo responde 404.
router = APIRouter(tags=["obras"], dependencies=[Depends(require_modulo("obras"))])


class SyncObrasRequest(BaseModel):
    municipio_ibge: str = Field(min_length=7, max_length=7)
    fontes: list[str] | None = None


@router.get("/works", response_model=list[ObraRead])
async def listar_obras(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    fonte: str | None = Query(default=None),
    situacao: str | None = Query(default=None),
    session: AsyncSession = Depends(get_rls_db),
) -> list[ObraRead]:
    rows = await service.listar(session, municipio=municipio, fonte=fonte, situacao=situacao)
    return await municipios_service.enriquecer(session, [ObraRead.model_validate(o) for o in rows])


@router.get("/works/summary", response_model=ObrasResumo)
async def obras_resumo(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    session: AsyncSession = Depends(get_rls_db),
) -> ObrasResumo:
    return await service.resumo(session, municipio=municipio)


@router.post("/works/sync", response_model=dict)
async def obras_sync(
    body: SyncObrasRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    # conta demo: coleta ativa é no-op (o cache responde; erro nunca aparece)
    if getattr(user, "is_demo", False):
        return {"gravados": 0, "demo": True}
    # sync_municipio é best-effort por fonte (registra erro em sync_runs e segue);
    # não lança em falha de fonte — devolve quantos registros gravou.
    n = await service.sync_municipio(
        session,
        usuario_id=user.id,
        municipio_ibge=body.municipio_ibge,
        fontes=body.fontes,
    )
    return {"gravados": n}
