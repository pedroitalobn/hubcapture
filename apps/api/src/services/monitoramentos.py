"""Monitoramentos — proposta-chave e busca de futuras propostas. RLS por usuario_id."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.monitoramento import Monitoramento, MonitoramentoBusca


async def listar(
    session: AsyncSession, usuario_id: uuid.UUID, apenas_ativos: bool = False
) -> list[Monitoramento]:
    stmt = select(Monitoramento).where(Monitoramento.usuario_id == usuario_id)
    if apenas_ativos:
        stmt = stmt.where(Monitoramento.ativo.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def criar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    proposta_id: uuid.UUID,
    canais: list[str],
    criterios: list[str] | None = None,
) -> Monitoramento:
    """Cria OU reconfigura o monitoramento (o POST é upsert: reenviar com
    outros critérios é como o usuário edita a escolha do multi-select)."""
    stmt = (
        pg_insert(Monitoramento)
        .values(
            usuario_id=usuario_id,
            proposta_id=proposta_id,
            ativo=True,
            canais=canais,
            criterios=criterios,
        )
        .on_conflict_do_update(
            constraint="uq_monitoramentos_usuario_proposta",
            set_={"ativo": True, "canais": canais, "criterios": criterios},
        )
        .returning(Monitoramento)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def desativar(
    session: AsyncSession, usuario_id: uuid.UUID, monitoramento_id: uuid.UUID
) -> None:
    await session.execute(
        update(Monitoramento)
        .where(
            Monitoramento.id == monitoramento_id,
            Monitoramento.usuario_id == usuario_id,
        )
        .values(ativo=False)
    )


# ── Busca de FUTURAS propostas (município + área/fonte) ─────────────────────
async def listar_buscas(session: AsyncSession, usuario_id: uuid.UUID) -> list[MonitoramentoBusca]:
    result = await session.execute(
        select(MonitoramentoBusca).where(MonitoramentoBusca.usuario_id == usuario_id)
    )
    return list(result.scalars().all())


async def criar_busca(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    *,
    municipio_ibge: str,
    area: str | None,
    fonte: str | None,
    canais: list[str],
    criterios: list[str] | None = None,
) -> MonitoramentoBusca:
    stmt = (
        pg_insert(MonitoramentoBusca)
        .values(
            usuario_id=usuario_id,
            municipio_ibge=municipio_ibge,
            area=area,
            fonte=fonte,
            ativo=True,
            canais=canais,
            criterios=criterios,
        )
        .on_conflict_do_update(
            constraint="uq_monitoramentos_busca_escopo",
            set_={"ativo": True, "canais": canais, "criterios": criterios},
        )
        .returning(MonitoramentoBusca)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def desativar_busca(
    session: AsyncSession, usuario_id: uuid.UUID, busca_id: uuid.UUID
) -> None:
    await session.execute(
        update(MonitoramentoBusca)
        .where(
            MonitoramentoBusca.id == busca_id,
            MonitoramentoBusca.usuario_id == usuario_id,
        )
        .values(ativo=False)
    )


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
