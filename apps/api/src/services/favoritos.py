"""Favoritos (usuario x proposta) — RLS por usuario_id."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.favorito import Favorito


async def listar(session: AsyncSession, usuario_id: uuid.UUID) -> list[Favorito]:
    result = await session.execute(
        select(Favorito).where(Favorito.usuario_id == usuario_id)
    )
    return list(result.scalars().all())


async def adicionar(
    session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID
) -> None:
    await session.execute(
        pg_insert(Favorito)
        .values(usuario_id=usuario_id, proposta_id=proposta_id)
        .on_conflict_do_nothing()
    )


async def remover(
    session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID
) -> None:
    await session.execute(
        delete(Favorito).where(
            Favorito.usuario_id == usuario_id, Favorito.proposta_id == proposta_id
        )
    )
