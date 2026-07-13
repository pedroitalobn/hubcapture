"""UserManager e a instância FastAPIUsers (dependencies de usuário atual)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import text

from ..db.user_db import get_user_db
from ..models.preferencias import PreferenciasUsuario
from ..models.usuario import Usuario
from .config import settings
from .security import auth_backend


class UserManager(UUIDIDMixin, BaseUserManager[Usuario, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_register(
        self, user: Usuario, request: Request | None = None
    ) -> None:
        # cria preferências default (onboarding preenche depois).
        # `preferencias_usuario` tem RLS: seta o tenant na transação atual para
        # o INSERT satisfazer a policy WITH CHECK (a sessão de auth não tem tenant).
        session = self.user_db.session  # type: ignore[attr-defined]
        await session.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"),
            {"uid": str(user.id)},
        )
        session.add(PreferenciasUsuario(usuario_id=user.id, monitorar_ativo=True))
        await session.commit()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[Usuario, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
# admin da plataforma (gestão de planos, convites, usuários)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
