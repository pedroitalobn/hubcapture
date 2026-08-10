"""Engine/sessão SQLAlchemy async + isolamento multi-tenant por RLS.

Regras de ouro (ver CLAUDE.md / plano):
- O runtime conecta como a role de app NÃO-superuser (settings.database_url).
  Superuser/BYPASSRLS ignoram policies silenciosamente => segurança falsa.
- O tenant é setado por request com `set_config('app.usuario_id', <uid>, true)`
  (is_local=true) DENTRO de uma transação. Nunca `SET` global — vazaria entre
  requests do pool de conexões.
- Login/registro rodam ANTES de existir usuario_id => usam `get_auth_session`
  (sem tenant). A tabela `usuarios` fica fora do RLS (isolamento por não expor
  endpoint de listagem); todas as demais tabelas por-tenant têm RLS.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_auth_session() -> AsyncIterator[AsyncSession]:
    """Sessão SEM tenant. Usada pelo fastapi-users (lookup por email no login,
    quando ainda não há usuario_id). Não use para dados por-tenant."""
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def rls_session(usuario_id: UUID | str) -> AsyncIterator[AsyncSession]:
    """Abre uma sessão com o tenant setado para toda a transação.

    Usada tanto pela dependency de request quanto por serviços/tests. O
    `set_config(..., true)` escopa o valor à transação atual; ao commit/rollback
    ele some, e a conexão só volta ao pool após o fim da transação — sem vazamento.
    """
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.usuario_id', :uid, true)"),
                {"uid": str(usuario_id)},
            )
            yield session
