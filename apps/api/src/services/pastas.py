"""Pastas do usuário e vínculo pasta↔proposta — RLS por usuario_id."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.pasta import Pasta, PastaProposta
from ..schemas.curadoria import PastaCreate, PastaUpdate


async def listar(session: AsyncSession, usuario_id: uuid.UUID) -> list[Pasta]:
    result = await session.execute(
        select(Pasta).where(Pasta.usuario_id == usuario_id).order_by(Pasta.created_at)
    )
    return list(result.scalars().all())


async def criar(
    session: AsyncSession, usuario_id: uuid.UUID, dados: PastaCreate
) -> Pasta:
    pasta = Pasta(usuario_id=usuario_id, nome=dados.nome, cor=dados.cor)
    session.add(pasta)
    await session.flush()
    return pasta


async def obter(
    session: AsyncSession, usuario_id: uuid.UUID, pasta_id: uuid.UUID
) -> Pasta | None:
    result = await session.execute(
        select(Pasta).where(Pasta.id == pasta_id, Pasta.usuario_id == usuario_id)
    )
    return result.scalar_one_or_none()


async def atualizar(
    session: AsyncSession, pasta: Pasta, dados: PastaUpdate
) -> Pasta:
    if dados.nome is not None:
        pasta.nome = dados.nome
    if dados.cor is not None:
        pasta.cor = dados.cor
    await session.flush()
    return pasta


async def adicionar_proposta(
    session: AsyncSession, pasta_id: uuid.UUID, proposta_id: uuid.UUID
) -> None:
    await session.execute(
        pg_insert(PastaProposta)
        .values(pasta_id=pasta_id, proposta_id=proposta_id)
        .on_conflict_do_nothing()
    )


async def remover_proposta(
    session: AsyncSession, pasta_id: uuid.UUID, proposta_id: uuid.UUID
) -> None:
    await session.execute(
        delete(PastaProposta).where(
            PastaProposta.pasta_id == pasta_id,
            PastaProposta.proposta_id == proposta_id,
        )
    )
