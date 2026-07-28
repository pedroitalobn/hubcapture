"""Busca de municípios por nome → código IBGE (para o onboarding conversacional)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.perfil import MunicipioBusca
from ...services import municipios as service

router = APIRouter(tags=["municipios"])


@router.get("/municipalities", response_model=list[MunicipioBusca])
async def buscar_municipios(
    q: str = Query(min_length=2, max_length=80),
    _user: Usuario = Depends(current_active_user),
) -> list[MunicipioBusca]:
    return [MunicipioBusca(**m) for m in await service.buscar(q)]
