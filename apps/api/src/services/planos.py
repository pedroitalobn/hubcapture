"""Planos da plataforma (catálogo) — nível-plataforma, sem RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plano import Plano
from ..schemas.planos import PlanoCreate, PlanoUpdate


async def listar(session: AsyncSession, apenas_ativos: bool = True) -> list[Plano]:
    stmt = select(Plano)
    if apenas_ativos:
        stmt = stmt.where(Plano.ativo.is_(True))
    stmt = stmt.order_by(Plano.preco_mensal.asc().nullsfirst())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def obter(session: AsyncSession, plano_id: uuid.UUID) -> Plano | None:
    return (
        await session.execute(select(Plano).where(Plano.id == plano_id))
    ).scalar_one_or_none()


async def criar(session: AsyncSession, dados: PlanoCreate) -> Plano:
    plano = Plano(**dados.model_dump())
    session.add(plano)
    await session.flush()
    return plano


async def atualizar(session: AsyncSession, plano: Plano, dados: PlanoUpdate) -> Plano:
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(plano, campo, valor)
    await session.flush()
    return plano
