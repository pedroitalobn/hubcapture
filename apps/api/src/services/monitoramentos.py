"""Monitoramentos de proposta-chave — RLS por usuario_id."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.monitoramento import Monitoramento


async def listar(session: AsyncSession, usuario_id: uuid.UUID) -> list[Monitoramento]:
    result = await session.execute(
        select(Monitoramento).where(Monitoramento.usuario_id == usuario_id)
    )
    return list(result.scalars().all())


async def criar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    proposta_id: uuid.UUID,
    canais: list[str],
) -> Monitoramento:
    stmt = (
        pg_insert(Monitoramento)
        .values(
            usuario_id=usuario_id, proposta_id=proposta_id, ativo=True, canais=canais
        )
        .on_conflict_do_update(
            constraint="uq_monitoramentos_usuario_proposta",
            set_={"ativo": True, "canais": canais},
        )
        .returning(Monitoramento)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def esta_monitorando(
    session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(Monitoramento.id).where(
            Monitoramento.usuario_id == usuario_id,
            Monitoramento.proposta_id == proposta_id,
            Monitoramento.ativo.is_(True),
        )
    )
    return result.first() is not None
