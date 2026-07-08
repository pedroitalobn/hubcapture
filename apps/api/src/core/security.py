"""Backend de autenticação JWT (fastapi-users) + estratégia de refresh.

- Access token: curto (settings.access_token_ttl), assinado com jwt_secret.
- Refresh token: longo (settings.refresh_token_ttl), assinado com jwt_refresh_secret.
O `sub` do JWT é o id do usuário — é ele que alimenta o RLS.
"""

from __future__ import annotations

from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

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
