"""Dispatch de alertas pelos canais (painel/email/wpp).

WhatsApp via Uniq (quando configurado + opt-in). painel é o default (o alerta já
está no banco); email é um hook (log) para uma fase futura.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import Proposta
from ..models.usuario import Usuario
from ..notifications import uniq
from . import alertas as alertas_service
from .municipios import rotulo


async def _propostas_dos_alertas(session: AsyncSession, alertas: list) -> dict:
    ids = {a.proposta_id for a in alertas if a.proposta_id}
    if not ids:
        return {}
    rows = (await session.execute(select(Proposta).where(Proposta.id.in_(ids)))).scalars()
    return {p.id: p for p in rows}


def _formatar(alertas: list, propostas: dict) -> str:
    """Cada linha abre pelo MUNICÍPIO (seção 23) — no WhatsApp o gestor precisa
    saber de qual território é o alerta antes de qualquer identificador."""
    linhas = []
    for a in alertas:
        p = propostas.get(a.proposta_id)
        municipio = rotulo(p.municipio_nome, p.uf, p.municipio_ibge) if p else "Seu território"
        objeto = (p.titulo if p and p.titulo else None) or "proposta acompanhada"
        linhas.append(f"🔔 {municipio} · {objeto} — {a.tipo or 'atualização'}")
    return "Hub Capture — atualizações:\n" + "\n".join(linhas)


async def despachar_wpp(session: AsyncSession, usuario: Usuario) -> int:
    """Envia os alertas não lidos do usuário por WhatsApp. Retorna quantos alertas
    entraram na mensagem (0 se sem opt-in/telefone/credencial ou sem alertas)."""
    if not (usuario.optin_wpp and usuario.telefone_wpp):
        return 0
    pendentes = await alertas_service.listar(session, usuario.id, apenas_nao_lidos=True)
    if not pendentes:
        return 0
    propostas = await _propostas_dos_alertas(session, pendentes)
    enviado = await uniq.enviar(usuario.telefone_wpp, _formatar(pendentes, propostas))
    return len(pendentes) if enviado else 0


async def responder_pergunta_wpp(telefone: str, resposta: str) -> bool:
    """Encaminha a resposta do chat ao WhatsApp do usuário."""
    return await uniq.enviar(telefone, resposta)


async def usuario_por_telefone(session: AsyncSession, telefone: str) -> Usuario | None:
    return (
        await session.execute(select(Usuario).where(Usuario.telefone_wpp == telefone))
    ).scalar_one_or_none()
