"""Backend de autenticação JWT (fastapi-users) + estratégia de refresh.

- Access token: curto (settings.access_token_ttl), assinado com jwt_secret.
- Refresh token: longo (settings.refresh_token_ttl), assinado com jwt_refresh_secret.
O `sub` do JWT é o id do usuário — é ele que alimenta o RLS.
"""

from __future__ import annotations

from fastapi import Response
from fastapi.security import APIKeyHeader
from fastapi_users import exceptions
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.authentication.strategy import StrategyDestroyNotSupportedError
from fastapi_users.authentication.transport import TransportLogoutNotSupportedError

from .config import settings

bearer_transport = BearerTransport(tokenUrl="api/v1/auth/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.jwt_secret,
        lifetime_seconds=settings.access_token_ttl,
    )


def get_refresh_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.jwt_refresh_secret,
        lifetime_seconds=settings.refresh_token_ttl,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# ── Chave de API de parceiro (§67) ──────────────────────────────────────────
# Segundo backend: `X-API-Key: hub_…` resolve para o USUÁRIO dono da chave, e
# daí para a frente é o fluxo de sempre — `get_rls_db` seta o tenant, os gates
# de plano/módulo valem. Volume e política de rotas ficam no middleware
# (`core/limite_api.py`), que roda antes e já recusou o que não pode passar.
class ApiKeyTransport:
    scheme = APIKeyHeader(
        name="X-API-Key",
        auto_error=False,
        description="Chave de API de integração (hub_live_… ou hub_test_…).",
    )

    async def get_login_response(self, token: str) -> Response:  # pragma: no cover
        raise TransportLogoutNotSupportedError()

    async def get_logout_response(self) -> Response:  # pragma: no cover
        raise TransportLogoutNotSupportedError()

    @staticmethod
    def get_openapi_login_responses_success() -> dict:  # pragma: no cover
        return {}

    @staticmethod
    def get_openapi_logout_responses_success() -> dict:  # pragma: no cover
        return {}


class ApiKeyStrategy:
    async def read_token(self, token: str | None, user_manager):  # noqa: ANN001
        if not token:
            return None
        from ..services import api_chaves

        chave = await api_chaves.resolver(token)
        if chave is None:
            return None
        try:
            user = await user_manager.get(chave.usuario_id)
        except exceptions.UserNotExists:
            return None
        # admin nunca entra por chave (defesa em profundidade: a emissão já recusa)
        if user.is_superuser:
            return None
        return user

    async def write_token(self, user) -> str:  # noqa: ANN001  # pragma: no cover
        raise NotImplementedError("chaves de API são emitidas em /account/api-keys")

    async def destroy_token(self, token: str, user) -> None:  # noqa: ANN001  # pragma: no cover
        raise StrategyDestroyNotSupportedError()


def get_api_key_strategy() -> ApiKeyStrategy:
    return ApiKeyStrategy()


api_key_backend = AuthenticationBackend(
    name="api_key",
    transport=ApiKeyTransport(),  # type: ignore[arg-type]
    get_strategy=get_api_key_strategy,  # type: ignore[arg-type]
)
