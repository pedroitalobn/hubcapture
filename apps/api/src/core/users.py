"""UserManager e a instância FastAPIUsers (dependencies de usuário atual)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import text, update

from ..db.user_db import get_user_db
from ..models.preferencias import PreferenciasUsuario
from ..models.usuario import Usuario
from ..notifications import email as email_service
from ..notifications import email_templates as templates
from ..services import config as config_service
from ..services import identidade as identidade_ctx
from .config import settings
from .security import api_key_backend, auth_backend


async def _app_base_url() -> str:
    return (await config_service.resolver("app_base_url")) or settings.app_base_url


async def _identidade(session, user: Usuario) -> identidade_ctx.Identidade:  # noqa: ANN001
    """Identidade da marca da conta (§69) — degrada para o Hub Capture."""
    from ..services import marcas as marcas_service

    try:
        return await marcas_service.identidade_do_usuario(session, user)
    except Exception:  # noqa: BLE001 — e-mail de conta nunca cai por causa da marca
        return identidade_ctx.PADRAO


async def _vincular_marca_do_host(session, user: Usuario, request: Request | None) -> None:  # noqa: ANN001
    """Cadastro feito no HOST de uma marca (subdomínio ou domínio próprio) com
    cadastro aberto entra na marca — e ganha o plano dela, se a conta não tem."""
    if request is None or user.marca_id:
        return
    from ..services import marcas as marcas_service

    marca = await marcas_service.por_host(
        session, marcas_service.host_da_requisicao(request.headers)
    )
    if marca is None or not marca.cadastro_aberto:
        return
    valores: dict = {"marca_id": marca.id}
    if marca.plano_id and not user.plano_id:
        valores["plano_id"] = marca.plano_id
    await session.execute(update(Usuario).where(Usuario.id == user.id).values(**valores))
    for chave, valor in valores.items():
        setattr(user, chave, valor)


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
        try:
            await _vincular_marca_do_host(session, user, request)
        except Exception:  # noqa: BLE001 — a marca nunca impede o cadastro
            pass
        await session.commit()
        # e-mail de boas-vindas (best-effort; desabilitado sem SMTP configurado)
        try:
            with identidade_ctx.usar(await _identidade(session, user)):
                assunto, txt, html = templates.boas_vindas(user.nome)
                await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001 — nunca derruba o registro por falha de e-mail
            pass

    async def on_after_forgot_password(
        self, user: Usuario, token: str, request: Request | None = None
    ) -> None:
        ident = await _identidade(self.user_db.session, user)  # type: ignore[attr-defined]
        url = f"{ident.url_base or await _app_base_url()}/reset-password?token={token}"
        try:
            with identidade_ctx.usar(ident):
                assunto, txt, html = templates.redefinir_senha(url)
                await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001
            pass

    async def on_after_request_verify(
        self, user: Usuario, token: str, request: Request | None = None
    ) -> None:
        ident = await _identidade(self.user_db.session, user)  # type: ignore[attr-defined]
        url = f"{ident.url_base or await _app_base_url()}/verify-email?token={token}"
        try:
            with identidade_ctx.usar(ident):
                assunto, txt, html = templates.verificar_email(url)
                await email_service.enviar(user.email, assunto, txt, html)
        except Exception:  # noqa: BLE001
            pass


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)


# JWT do painel primeiro; a chave de API de parceiro (§67) é o segundo caminho.
# Só o backend JWT tem rotas de login montadas (api/v1/auth.py).
fastapi_users = FastAPIUsers[Usuario, uuid.UUID](
    get_user_manager, [auth_backend, api_key_backend]
)

current_active_user = fastapi_users.current_user(active=True)
# admin da plataforma (gestão de planos, convites, usuários)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
# resolução OPCIONAL (guards que rodam antes da auth do endpoint, ex.
# require_modulo): sem token/token inválido → None, nunca 401 daqui.
current_user_optional = fastapi_users.current_user(active=True, optional=True)
