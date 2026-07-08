"""Alertas — listagem, marcação de lido e geração quando há monitoramento.

RLS por usuario_id. `gerar_se_monitorado` roda no contexto (sessão/tenant) do
próprio usuário: se ele monitora a proposta, cria o alerta (WITH CHECK ok).
O cron global multi-tenant (n8n, papel com BYPASSRLS) é evolução futura.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alerta import Alerta
from . import monitoramentos as mon_service


async def listar(
    session: AsyncSession, usuario_id: uuid.UUID, apenas_nao_lidos: bool = False
) -> list[Alerta]:
    stmt = select(Alerta).where(Alerta.usuario_id == usuario_id)
    if apenas_nao_lidos:
        stmt = stmt.where(Alerta.lido.is_(False))
    stmt = stmt.order_by(Alerta.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def marcar_lido(
    session: AsyncSession, usuario_id: uuid.UUID, alerta_id: uuid.UUID
) -> None:
    await session.execute(
        update(Alerta)
        .where(Alerta.id == alerta_id, Alerta.usuario_id == usuario_id)
        .values(lido=True)
    )


async def gerar_se_monitorado(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    proposta_id: uuid.UUID,
    tipo: str,
    payload: dict,
) -> Alerta | None:
    """Cria um alerta se o usuário monitora a proposta; senão retorna None."""
    if not await mon_service.esta_monitorando(session, usuario_id, proposta_id):
        return None
    alerta = Alerta(
        usuario_id=usuario_id, proposta_id=proposta_id, tipo=tipo, payload=payload
    )
    session.add(alerta)
    await session.flush()
    return alerta
