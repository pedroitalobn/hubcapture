"""Conexão das agendas externas (Google/Microsoft/Apple/CardDAV).

Guarda uma linha por conta conectada, com as credenciais **cifradas**
(`core/crypto`). A API nunca devolve token/senha — só status.

O `state` do OAuth é assinado (HMAC do `jwt_secret`) e tem validade curta: sem
isso, um terceiro poderia devolver um `code` de outra conta no callback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.crypto import cifrar_json, decifrar_json
from ..integrations.contatos import get_provedor, provedores
from ..integrations.contatos import oauth as oauth_mod
from ..integrations.contatos.base import Credencial
from ..models.integracao_contatos import IntegracaoContatos
from ..schemas.contato import (
    AutorizacaoOAuth,
    CallbackOAuth,
    ConectarSenhaApp,
    IntegracaoUpdate,
    ProvedorInfo,
)

STATE_TTL = 600  # 10 min entre pedir a autorização e voltar do provedor

INSTRUCOES = {
    "google": "Conecte sua Conta Google e autorize o acesso aos contatos.",
    "microsoft": "Conecte sua conta Microsoft 365/Outlook.",
    "apple": (
        "Use seu Apple ID e uma SENHA DE APP gerada em appleid.apple.com → "
        "Segurança → Senhas de app (a senha da conta não funciona)."
    ),
    "carddav": "Informe a URL do servidor CardDAV, usuário e senha.",
}


class IntegracaoErro(Exception):
    """Falha de conexão/credencial — vira 400 no endpoint."""


# ── catálogo e leitura ───────────────────────────────────────────────────────


async def catalogo() -> list[ProvedorInfo]:
    saida: list[ProvedorInfo] = []
    for prov in provedores():
        saida.append(
            ProvedorInfo(
                provedor=prov.provedor_id,
                rotulo=prov.rotulo,
                tipo_auth=prov.tipo_auth,
                disponivel=await prov.disponivel(),
                instrucoes=INSTRUCOES.get(prov.provedor_id),
            )
        )
    return saida


async def listar(session: AsyncSession) -> list[IntegracaoContatos]:
    stmt = select(IntegracaoContatos).order_by(
        IntegracaoContatos.provedor, IntegracaoContatos.conta
    )
    return list((await session.execute(stmt)).scalars().all())


async def obter(session: AsyncSession, integracao_id: uuid.UUID) -> IntegracaoContatos | None:
    return (
        await session.execute(
            select(IntegracaoContatos).where(IntegracaoContatos.id == integracao_id)
        )
    ).scalar_one_or_none()


# ── credenciais ──────────────────────────────────────────────────────────────


def credencial(integracao: IntegracaoContatos) -> Credencial:
    return Credencial(conta=integracao.conta, dados=decifrar_json(integracao.credenciais))


def salvar_credencial(integracao: IntegracaoContatos, cred: Credencial) -> None:
    if cred.alterada:
        integracao.credenciais = cifrar_json(cred.dados)
        cred.alterada = False


# ── OAuth (state assinado) ───────────────────────────────────────────────────


def _assinar(payload: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def gerar_state(provedor: str, usuario_id: uuid.UUID) -> str:
    corpo = json.dumps(
        {
            "p": provedor,
            "u": str(usuario_id),
            "n": secrets.token_urlsafe(8),
            "e": int(time.time()) + STATE_TTL,
        },
        sort_keys=True,
    )
    dados = base64.urlsafe_b64encode(corpo.encode()).decode().rstrip("=")
    return f"{dados}.{_assinar(dados)}"


def validar_state(state: str | None, provedor: str, usuario_id: uuid.UUID) -> bool:
    if not state or "." not in state:
        return False
    dados, _, assinatura = state.partition(".")
    if not hmac.compare_digest(assinatura, _assinar(dados)):
        return False
    try:
        corpo = json.loads(base64.urlsafe_b64decode(dados + "=" * (-len(dados) % 4)))
    except (ValueError, json.JSONDecodeError):
        return False
    return (
        corpo.get("p") == provedor
        and corpo.get("u") == str(usuario_id)
        and int(corpo.get("e", 0)) > int(time.time())
    )


async def iniciar_oauth(
    *, provedor: str, usuario_id: uuid.UUID, redirect_uri: str | None = None
) -> AutorizacaoOAuth:
    try:
        app = oauth_mod.app_oauth(provedor)
    except KeyError as exc:
        raise IntegracaoErro(f"provedor sem OAuth: {provedor}") from exc
    if not await oauth_mod.configurado(app):
        raise IntegracaoErro(
            f"{provedor}: credenciais de aplicação não configuradas "
            "(painel admin → Configurações → integrações)"
        )
    state = gerar_state(provedor, usuario_id)
    url = await oauth_mod.url_autorizacao(app, state, redirect_uri)
    return AutorizacaoOAuth(url=url, state=state)


async def _upsert(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    provedor: str,
    conta: str,
    dados_credencial: dict,
    direcao: str,
) -> IntegracaoContatos:
    """Reconectar a mesma conta atualiza a linha (mantém vínculos e histórico)."""
    existente = (
        await session.execute(
            select(IntegracaoContatos).where(
                IntegracaoContatos.provedor == provedor,
                IntegracaoContatos.conta == conta,
            )
        )
    ).scalar_one_or_none()
    integracao = existente or IntegracaoContatos(
        usuario_id=usuario_id, provedor=provedor, conta=conta
    )
    integracao.credenciais = cifrar_json(dados_credencial)
    integracao.direcao = direcao
    integracao.status = "conectada"
    integracao.ultimo_erro = None
    integracao.ativo = True
    if existente is None:
        session.add(integracao)
    await session.flush()
    return integracao


async def finalizar_oauth(
    session: AsyncSession, *, usuario_id: uuid.UUID, callback: CallbackOAuth
) -> IntegracaoContatos:
    if not validar_state(callback.state, callback.provedor, usuario_id):
        raise IntegracaoErro("state inválido ou expirado — refaça a conexão")
    try:
        app = oauth_mod.app_oauth(callback.provedor)
        tokens = await oauth_mod.trocar_codigo(app, callback.code, callback.redirect_uri)
    except (KeyError, ValueError) as exc:
        raise IntegracaoErro(str(exc)) from exc

    provedor = get_provedor(callback.provedor)
    cred = Credencial(conta="", dados=tokens)
    conta = await provedor.identidade(cred)
    return await _upsert(
        session,
        usuario_id=usuario_id,
        provedor=callback.provedor,
        conta=conta,
        dados_credencial=cred.dados,
        direcao=callback.direcao,
    )


async def conectar_senha_app(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    provedor: str,
    dados: ConectarSenhaApp,
) -> IntegracaoContatos:
    prov = get_provedor(provedor)
    if prov.tipo_auth != "senha_app":
        raise IntegracaoErro(f"{provedor} usa OAuth, não senha de app")
    credenciais = {"senha_app": dados.senha_app}
    if dados.base_url:
        credenciais["base_url"] = dados.base_url
    cred = Credencial(conta=dados.conta, dados=credenciais)
    try:
        await prov.identidade(cred)  # valida credencial e descobre a agenda
    except Exception as exc:  # noqa: BLE001 — vira 400 com a causa
        raise IntegracaoErro(f"não foi possível conectar: {exc}") from exc
    return await _upsert(
        session,
        usuario_id=usuario_id,
        provedor=provedor,
        conta=dados.conta,
        dados_credencial=cred.dados,
        direcao=dados.direcao,
    )


async def atualizar(
    session: AsyncSession, integracao: IntegracaoContatos, dados: IntegracaoUpdate
) -> IntegracaoContatos:
    if dados.direcao is not None:
        integracao.direcao = dados.direcao
    if dados.ativo is not None:
        integracao.ativo = dados.ativo
    await session.flush()
    return integracao


async def desconectar(session: AsyncSession, integracao: IntegracaoContatos) -> None:
    """Remove a conexão e os vínculos (cascade). Os contatos ficam na agenda."""
    await session.delete(integracao)
    await session.flush()
