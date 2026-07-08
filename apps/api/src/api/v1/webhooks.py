"""Webhook de entrada do WhatsApp (Uniq).

Fluxo: Uniq → este webhook → mapeia telefone→usuário → chat RAG com a RLS do
usuário → resposta de volta pelo Uniq. Público, validado por token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...ai import chat as ai_chat
from ...db.session import rls_session
from ...notifications import uniq
from ...services import dispatch_alerts, rag
from ..deps import get_platform_db

router = APIRouter(tags=["webhooks"])


class UniqInbound(BaseModel):
    telefone: str
    mensagem: str
    token: str | None = None


@router.post("/webhooks/uniq")
async def uniq_inbound(
    body: UniqInbound,
    session: AsyncSession = Depends(get_platform_db),
) -> dict:
    if not await uniq.validar_webhook(body.token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "WEBHOOK_TOKEN_INVALIDO")

    usuario = await dispatch_alerts.usuario_por_telefone(session, body.telefone)
    if usuario is None:
        return {"ok": True, "ignorado": "telefone_nao_reconhecido"}

    papel = usuario.papel or "executivo"
    async with rls_session(usuario.id) as s:
        propostas = await rag.buscar_propostas(s, body.mensagem)
        contexto = rag.montar_contexto(propostas)
    resposta = await ai_chat.responder(contexto, body.mensagem, papel)
    enviado = await dispatch_alerts.responder_pergunta_wpp(body.telefone, resposta)
    return {"ok": True, "respondido": enviado}
