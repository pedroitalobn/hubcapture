"""Dependencies compartilhadas dos endpoints.

`get_rls_db` é a porta de entrada de dados por-tenant: resolve o usuário atual
pelo JWT (via fastapi-users) e abre uma sessão com `app.usuario_id` setado para
toda a transação. Todo endpoint que lê/escreve dado por-tenant usa esta sessão.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.users import current_active_user
from ..db.session import SessionLocal, plataforma_session, rls_session
from ..models.usuario import Usuario


async def get_rls_db(
    user: Usuario = Depends(current_active_user),
) -> AsyncIterator[AsyncSession]:
    async with rls_session(user.id) as session:
        yield session


async def get_plataforma_db() -> AsyncIterator[AsyncSession]:
    """Sessão de plataforma que TAMBÉM alcança tabelas por-tenant marcadas
    (hoje só `demandas`, a fila da assessoria). Usar apenas em rotas de admin."""
    async with plataforma_session() as session:
        yield session


async def get_platform_db() -> AsyncIterator[AsyncSession]:
    """Sessão para tabelas de nível-plataforma (planos, convites) — sem tenant/RLS.
    Abre uma transação e commita ao final do request."""
    async with SessionLocal() as session:
        async with session.begin():
            yield session
