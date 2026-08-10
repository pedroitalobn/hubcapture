"""Endpoints de planos. Listagem pública; criação/edição só admin (is_superuser)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser, current_user_optional
from ...models.usuario import Usuario
from ...schemas.planos import (
    OpcaoCatalogo,
    PlanoCreate,
    PlanoOpcoes,
    PlanoRead,
    PlanoUpdate,
)
from ...services import fontes as fontes_service
from ...services import modulos as modulos_service
from ...services import plano_gates
from ...services import planos as service
from ..deps import get_platform_db

router = APIRouter(tags=["planos"])


@router.get("/plans/options", response_model=PlanoOpcoes)
async def opcoes_de_config(
    _admin: Usuario = Depends(current_superuser),
) -> PlanoOpcoes:
    """Catálogos do editor de config do plano: módulos, fontes (grupos) e
    features conhecidas. O que não estiver aqui não é gate válido."""
    return PlanoOpcoes(
        modulos=[
            OpcaoCatalogo(**{k: m[k] for k in ("chave", "label", "descricao")})
            for m in modulos_service.MODULOS
        ],
        fontes=[
            OpcaoCatalogo(chave=g["chave"], label=g["label"], descricao=g["descricao"])
            for g in fontes_service.catalogo()
        ],
        features=[OpcaoCatalogo(**f) for f in plano_gates.FEATURES],
    )


@router.get("/plans", response_model=list[PlanoRead])
async def listar_planos(
    incluir_inativos: bool = Query(
        default=False, description="planos inativos também (só p/ administrador)"
    ),
    user: Usuario | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_platform_db),
) -> list[PlanoRead]:
    # a listagem é pública (pricing); os inativos só existem p/ o admin gerir
    admin = user is not None and user.is_superuser
    rows = await service.listar(session, apenas_ativos=not (incluir_inativos and admin))
    return [PlanoRead.model_validate(r) for r in rows]


@router.post("/plans", response_model=PlanoRead, status_code=status.HTTP_201_CREATED)
async def criar_plano(
    body: PlanoCreate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> PlanoRead:
    plano = await service.criar(session, body)
    return PlanoRead.model_validate(plano)


@router.patch("/plans/{plano_id}", response_model=PlanoRead)
async def atualizar_plano(
    plano_id: uuid.UUID,
    body: PlanoUpdate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> PlanoRead:
    plano = await service.obter(session, plano_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PLANO_NAO_ENCONTRADO")
    plano = await service.atualizar(session, plano, body)
    return PlanoRead.model_validate(plano)
