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
from ..db.session import rls_session
from ..models.usuario import Usuario


async def get_rls_db(
    user: Usuario = Depends(current_active_user),
) -> AsyncIterator[AsyncSession]:
    async with rls_session(user.id) as session:
        yield session
