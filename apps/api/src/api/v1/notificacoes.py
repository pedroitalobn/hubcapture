"""Canais de notificação da conta + inscrições de Web Push (§63)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...notifications import webpush
from ...services import canais_alerta as service
from ...services import plano_gates
from ...services.modulos import require_modulo
from ..deps import get_rls_db

router = APIRouter(tags=["notificacoes"], dependencies=[Depends(require_modulo("alertas"))])


class PreferenciasNotificacao(BaseModel):
    email: bool
    wpp: bool
    telefone_wpp: str | None = None
    push_inscricoes: int
    # o plano pode não incluir e-mail/WhatsApp (§39): a tela avisa em vez de
    # deixar o gestor ligar um canal que a varredura vai descartar
    email_no_plano: bool = True
    wpp_no_plano: bool = True


class PreferenciasUpdate(BaseModel):
    email: bool


class ChavesInscricao(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class InscricaoPush(BaseModel):
    """O `PushSubscription.toJSON()` do navegador, como ele vem."""

    endpoint: str = Field(min_length=10, max_length=2048)
    keys: ChavesInscricao


class CancelarPush(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)


async def _preferencias(session: AsyncSession, user: Usuario) -> PreferenciasNotificacao:
    cfg = await plano_gates.config_do_usuario(session, user.id)
    return PreferenciasNotificacao(
        email="email" in await service.preferidos(session, user.id),
        wpp=bool(user.optin_wpp and user.telefone_wpp),
        telefone_wpp=user.telefone_wpp,
        push_inscricoes=len(await service.inscricoes(session, user.id)),
        email_no_plano=plano_gates.feature_liberada(cfg, "alertas_email"),
        wpp_no_plano=plano_gates.feature_liberada(cfg, "alertas_wpp"),
    )


@router.get("/notifications/preferences", response_model=PreferenciasNotificacao)
async def ler_preferencias(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PreferenciasNotificacao:
    return await _preferencias(session, user)


@router.put("/notifications/preferences", response_model=PreferenciasNotificacao)
async def salvar_preferencias(
    body: PreferenciasUpdate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PreferenciasNotificacao:
    await service.definir_preferidos(session, user.id, ["email"] if body.email else [])
    return await _preferencias(session, user)


@router.get("/notifications/push/key")
async def chave_publica(_: Usuario = Depends(current_active_user)) -> dict:
    """A `applicationServerKey` que o navegador usa para se inscrever."""
    chaves = await webpush.garantir_chaves()
    return {"chave_publica": chaves.publica}


@router.post("/notifications/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def inscrever(
    body: InscricaoPush,
    user_agent: str | None = Header(default=None),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    if not webpush.endpoint_permitido(body.endpoint):
        # o endpoint vira destino de um POST do servidor: só os serviços de
        # push dos navegadores — qualquer outro host seria SSRF por procuração
        raise HTTPException(status_code=422, detail="endpoint de push inválido")
    await service.inscrever(
        session,
        user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=user_agent,
    )


@router.post("/notifications/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar(
    body: CancelarPush,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.cancelar(session, user.id, body.endpoint)


@router.post("/notifications/push/test")
async def testar(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    """Manda uma notificação de teste a todos os navegadores inscritos."""
    resultado = await service.enviar_push(
        session,
        user.id,
        {
            "title": "Hub Capture · notificações ativas",
            "body": "Você vai receber aqui os alertas das propostas que acompanha.",
            "url": "/panel/alerts",
            "tag": "teste",
        },
    )
    return resultado
