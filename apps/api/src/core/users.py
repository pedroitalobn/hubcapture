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
from ..notifications import email as email_service
from ..notifications import email_templates as templates
from ..services import config as config_service
from .config import settings
from .security import auth_backend


async def _app_base_url() -> str:
    return (await config_service.resolver("app_base_url")) or settings.app_base_url


class UserManager(UUIDIDMixin, BaseUserManager[Usuario, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_register(self, user: Usuario, request: Request | None = None) -> None:
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
        # e-mail de boas-vindas (best-effort; desabilitado sem SMTP configurado)
        try:
            assunto, txt, html = templates.boas_vindas(user.nome)
            await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001 — nunca derruba o registro por falha de e-mail
            pass

    async def on_after_forgot_password(
        self, user: Usuario, token: str, request: Request | None = None
    ) -> None:
        url = f"{await _app_base_url()}/reset-password?token={token}"
        assunto, txt, html = templates.redefinir_senha(url)
        try:
            await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001
            pass

    async def on_after_request_verify(
        self, user: Usuario, token: str, request: Request | None = None
    ) -> None:
        url = f"{await _app_base_url()}/verify-email?token={token}"
        assunto, txt, html = templates.verificar_email(url)
        try:
            await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001
            pass


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[Usuario, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
# admin da plataforma (gestão de planos, convites, usuários)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
# resolução OPCIONAL (guards que rodam antes da auth do endpoint, ex.
# require_modulo): sem token/token inválido → None, nunca 401 daqui.
current_user_optional = fastapi_users.current_user(active=True, optional=True)
