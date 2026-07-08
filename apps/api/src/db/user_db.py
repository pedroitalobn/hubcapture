"""Adapter do fastapi-users sobre a tabela `usuarios`.

Usa a sessão de AUTH (sem tenant): o login busca por email antes de existir
usuario_id, e `usuarios` não tem RLS.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.usuario import Usuario
from .session import get_auth_session


async def get_user_db(
    session: AsyncSession = Depends(get_auth_session),
) -> AsyncIterator[SQLAlchemyUserDatabase]:
    yield SQLAlchemyUserDatabase(session, Usuario)
