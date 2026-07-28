"""Dispatch de alertas pelos canais (painel/email/wpp).

WhatsApp via Uniq (quando configurado + opt-in). painel é o default (o alerta já
está no banco); email é um hook (log) para uma fase futura.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.usuario import Usuario
from ..notifications import uniq
from . import alertas as alertas_service


def _formatar(alertas: list) -> str:
    linhas = [f"🔔 {a.tipo or 'alerta'}: proposta {a.proposta_id}" for a in alertas]
    return "Hub Capture — atualizações:\n" + "\n".join(linhas)


async def despachar_wpp(session: AsyncSession, usuario: Usuario) -> int:
    """Envia os alertas não lidos do usuário por WhatsApp. Retorna quantos alertas
    entraram na mensagem (0 se sem opt-in/telefone/credencial ou sem alertas)."""
    if not (usuario.optin_wpp and usuario.telefone_wpp):
        return 0
    pendentes = await alertas_service.listar(session, usuario.id, apenas_nao_lidos=True)
    if not pendentes:
        return 0
    enviado = await uniq.enviar(usuario.telefone_wpp, _formatar(pendentes))
    return len(pendentes) if enviado else 0


async def responder_pergunta_wpp(telefone: str, resposta: str) -> bool:
    """Encaminha a resposta do chat ao WhatsApp do usuário."""
    return await uniq.enviar(telefone, resposta)


async def usuario_por_telefone(session: AsyncSession, telefone: str) -> Usuario | None:
    return (
        await session.execute(select(Usuario).where(Usuario.telefone_wpp == telefone))
    ).scalar_one_or_none()
