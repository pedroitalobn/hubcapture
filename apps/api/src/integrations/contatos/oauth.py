"""OAuth2 (authorization code + refresh) para Google e Microsoft.

As credenciais de APLICAÇÃO (client id/secret) vêm do painel admin
(`services/config`), como todo provider do Hub: sem elas, o provedor aparece
como indisponível na UI em vez de estourar erro.

O `redirect_uri` padrão aponta para a página do web (`/integracoes/callback`),
derivada de `app_base_url` — a mesma base usada nos links de e-mail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ...services import config as config_service
from ._http import request_json

CAMINHO_CALLBACK = "/integracoes/callback"


@dataclass(frozen=True)
class AppOAuth:
    provedor_id: str
    auth_url: str
    token_url: str
    escopos: list[str]
    chave_client_id: str
    chave_client_secret: str
    params_extra: dict[str, str] = field(default_factory=dict)


GOOGLE = AppOAuth(
    provedor_id="google",
    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    escopos=[
        "https://www.googleapis.com/auth/contacts",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
    chave_client_id="google_client_id",
    chave_client_secret="google_client_secret",
    # offline+consent são o que garante REFRESH TOKEN (sem ele, a conexão morre
    # em 1h e o sync agendado nunca roda).
    params_extra={"access_type": "offline", "prompt": "consent"},
)

MICROSOFT = AppOAuth(
    provedor_id="microsoft",
    auth_url="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    escopos=[
        "offline_access",
        "https://graph.microsoft.com/Contacts.ReadWrite",
        "https://graph.microsoft.com/User.Read",
    ],
    chave_client_id="microsoft_client_id",
    chave_client_secret="microsoft_client_secret",
    params_extra={"response_mode": "query"},
)

_APPS = {GOOGLE.provedor_id: GOOGLE, MICROSOFT.provedor_id: MICROSOFT}


def app_oauth(provedor_id: str) -> AppOAuth:
    return _APPS[provedor_id]


async def _tenant() -> str:
    return await config_service.resolver("microsoft_tenant") or "common"


async def _url(app: AppOAuth, bruta: str) -> str:
    return bruta.format(tenant=await _tenant()) if "{tenant}" in bruta else bruta


async def credenciais_app(app: AppOAuth) -> tuple[str | None, str | None]:
    return (
        await config_service.resolver(app.chave_client_id),
        await config_service.resolver(app.chave_client_secret),
    )


async def configurado(app: AppOAuth) -> bool:
    client_id, secret = await credenciais_app(app)
    return bool(client_id and secret)


async def redirect_uri_padrao() -> str:
    base = await config_service.resolver("app_base_url") or "http://localhost:3000"
    return base.rstrip("/") + CAMINHO_CALLBACK


async def url_autorizacao(app: AppOAuth, state: str, redirect_uri: str | None) -> str:
    client_id, _ = await credenciais_app(app)
    if not client_id:
        raise ValueError(f"{app.provedor_id}: client id não configurado")
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or await redirect_uri_padrao(),
        "response_type": "code",
        "scope": " ".join(app.escopos),
        "state": state,
        **app.params_extra,
    }
    return f"{await _url(app, app.auth_url)}?{urlencode(params)}"


def _com_expiracao(tokens: dict, anteriores: dict | None = None) -> dict:
    """Normaliza a resposta de token: guarda o instante de expiração absoluto.

    Renovação do Google costuma vir SEM refresh_token — preserva o antigo, senão
    a conexão se perde na primeira renovação.
    """
    dados = dict(anteriores or {})
    dados["access_token"] = tokens.get("access_token")
    if tokens.get("refresh_token"):
        dados["refresh_token"] = tokens["refresh_token"]
    # 60s de folga para não usar um token que expira no meio da chamada
    dados["expira_em"] = int(time.time()) + int(tokens.get("expires_in", 3600)) - 60
    return dados


async def trocar_codigo(app: AppOAuth, code: str, redirect_uri: str | None) -> dict:
    client_id, secret = await credenciais_app(app)
    if not (client_id and secret):
        raise ValueError(f"{app.provedor_id}: credenciais de aplicação ausentes")
    resposta = await request_json(
        "POST",
        await _url(app, app.token_url),
        data={
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri or await redirect_uri_padrao(),
            "grant_type": "authorization_code",
        },
    )
    return _com_expiracao(resposta)


async def renovar(app: AppOAuth, dados: dict) -> dict:
    refresh_token = dados.get("refresh_token")
    if not refresh_token:
        raise ValueError(f"{app.provedor_id}: sem refresh token — reconecte a conta")
    client_id, secret = await credenciais_app(app)
    if not (client_id and secret):
        raise ValueError(f"{app.provedor_id}: credenciais de aplicação ausentes")
    payload = {
        "client_id": client_id,
        "client_secret": secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if app.provedor_id == "microsoft":
        payload["scope"] = " ".join(app.escopos)
    resposta = await request_json("POST", await _url(app, app.token_url), data=payload)
    return _com_expiracao(resposta, dados)


def expirado(dados: dict) -> bool:
    return int(dados.get("expira_em", 0)) <= int(time.time())
