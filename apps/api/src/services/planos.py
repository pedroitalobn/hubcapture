"""Planos da plataforma (catálogo) — nível-plataforma, sem RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plano import Plano
from ..schemas.planos import PlanoCreate, PlanoUpdate
from . import plano_gates


async def listar(session: AsyncSession, apenas_ativos: bool = True) -> list[Plano]:
    stmt = select(Plano)
    if apenas_ativos:
        stmt = stmt.where(Plano.ativo.is_(True))
    stmt = stmt.order_by(Plano.preco_mensal.asc().nullsfirst())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def obter(session: AsyncSession, plano_id: uuid.UUID) -> Plano | None:
    return (await session.execute(select(Plano).where(Plano.id == plano_id))).scalar_one_or_none()


async def criar(session: AsyncSession, dados: PlanoCreate) -> Plano:
    valores = dados.model_dump()
    if dados.limites is not None:
        valores["limites"] = dados.limites.como_jsonb()
    plano = Plano(**valores)
    session.add(plano)
    await session.flush()
    # o guard de módulo lê a config por snapshot; editar plano propaga já
    plano_gates.limpar_cache()
    return plano


async def atualizar(session: AsyncSession, plano: Plano, dados: PlanoUpdate) -> Plano:
    valores = dados.model_dump(exclude_unset=True)
    if valores.get("limites") is not None and dados.limites is not None:
        valores["limites"] = dados.limites.como_jsonb()
    for campo, valor in valores.items():
        setattr(plano, campo, valor)
    await session.flush()
    plano_gates.limpar_cache()
    return plano
