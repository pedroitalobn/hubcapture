"""Job sync_contatos — sincroniza as agendas conectadas de cada usuário.

Alvo do cron do n8n (diário/horário). Cada usuário roda na SUA sessão com RLS
(`rls_session`), então a varredura global não precisa de role BYPASSRLS: a
listagem de quem tem integração ativa é feita uma vez, fora do tenant.

Best-effort em dois níveis: um usuário que falha não derruba os outros, e dentro
do usuário uma integração que falha não derruba as demais (`sincronizar_todas`).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from ..db.session import SessionLocal, rls_session
from ..models.integracao_contatos import IntegracaoContatos
from ..schemas.contato import SyncResultado
from ..services import contatos_sync

log = logging.getLogger("hubcapture.jobs.contatos")


async def _usuarios_com_integracao() -> list[uuid.UUID]:
    # roda sem tenant: precisa enxergar todas as contas conectadas
    async with SessionLocal() as session:
        stmt = select(IntegracaoContatos.usuario_id).where(
            IntegracaoContatos.ativo.is_(True)
        ).distinct()
        return list((await session.execute(stmt)).scalars().all())


async def sync_contatos_usuario(usuario_id: uuid.UUID) -> list[SyncResultado]:
    async with rls_session(usuario_id) as session:
        resultados = await contatos_sync.sincronizar_todas(
            session, usuario_id=usuario_id, tipo="agendado"
        )
        await contatos_sync.limpar_arquivados(session)
        return resultados


async def sync_contatos_todos() -> int:
    """Roda o sync de todos os usuários com agenda conectada. Retorna quantos rodaram."""
    total = 0
    for usuario_id in await _usuarios_com_integracao():
        try:
            await sync_contatos_usuario(usuario_id)
            total += 1
        except Exception:  # noqa: BLE001 — incidente já vai para sync_runs
            log.warning("sync de contatos falhou para %s", usuario_id, exc_info=True)
    return total
