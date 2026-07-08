"""Copiloto — recuperação na base de conhecimento (docs/tutoriais TransfereGov)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base_conhecimento import BaseConhecimento


async def buscar_conhecimento(
    session: AsyncSession, query: str, k: int = 3
) -> list[BaseConhecimento]:
    like = f"%{query}%"
    stmt = (
        select(BaseConhecimento)
        .where(
            or_(
                BaseConhecimento.titulo.ilike(like),
                BaseConhecimento.conteudo.ilike(like),
            )
        )
        .limit(k)
    )
    return list((await session.execute(stmt)).scalars().all())


def montar_contexto(itens: list[BaseConhecimento]) -> str:
    if not itens:
        return "(sem material na base de conhecimento; responda com orientação geral)"
    return "\n\n".join(f"## {i.titulo}\n{i.conteudo}" for i in itens)
