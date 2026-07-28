"""Favoritos (usuario x proposta) — RLS por usuario_id."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.favorito import Favorito
from ..models.proposta import Proposta


async def listar(session: AsyncSession, usuario_id: uuid.UUID) -> list[Favorito]:
    result = await session.execute(select(Favorito).where(Favorito.usuario_id == usuario_id))
    return list(result.scalars().all())


async def adicionar(session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID) -> None:
    await session.execute(
        pg_insert(Favorito)
        .values(usuario_id=usuario_id, proposta_id=proposta_id)
        .on_conflict_do_nothing()
    )


async def remover(session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID) -> None:
    await session.execute(
        delete(Favorito).where(
            Favorito.usuario_id == usuario_id, Favorito.proposta_id == proposta_id
        )
    )


async def listar_propostas(session: AsyncSession, usuario_id: uuid.UUID) -> list[Proposta]:
    """Propostas favoritadas COMPLETAS (join), para a aba de acompanhamento.

    O RLS de propostas ainda vale: favorita de um município que saiu do
    território não aparece (comportamento correto — sem vazamento)."""
    result = await session.execute(
        select(Proposta)
        .join(Favorito, Favorito.proposta_id == Proposta.id)
        .where(Favorito.usuario_id == usuario_id)
        .order_by(Favorito.created_at.desc())
    )
    return list(result.scalars().all())
