"""Canais de alerta da CONTA + entrega por Web Push (§63).

POR QUE EXISTE: os canais viviam só no monitoramento, e toda porta de criação
de monitoramento gravava `canais=['painel']` fixo — favoritar, o 🔔 do detalhe,
a lista da Captação. Resultado: o gestor ligava o WhatsApp na conta (opt-in +
telefone) e nenhum alerta de proposta saía por lá; só as buscas criadas no
onboarding carregavam outro canal. "Notificação não funciona" era isso.

A regra agora: os canais efetivos de um lote de alertas são a UNIÃO dos canais
de quem gerou o alerta (monitoramento/busca) com os canais da conta:

- **e-mail** — escolhido na conta (`preferencias_usuario.canais_alerta`);
- **WhatsApp** — o opt-in da conta (`usuarios.optin_wpp` + telefone), que é o
  interruptor que o gestor já conhece em "Minha conta";
- **push** — existe inscrição de navegador (`push_inscricoes`): a permissão
  concedida no navegador É o opt-in.

O plano (§39) continua podando e-mail/WhatsApp na varredura.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.preferencias import PreferenciasUsuario
from ..models.push_inscricao import PushInscricao
from ..models.usuario import Usuario
from ..notifications import webpush

log = logging.getLogger("hubcapture.canais_alerta")

#: canais que a CONTA escolhe explicitamente (os outros derivam de opt-in)
CANAIS_DA_CONTA = ("email",)


async def preferidos(session: AsyncSession, usuario_id: uuid.UUID) -> list[str]:
    pref = (
        await session.execute(
            select(PreferenciasUsuario.canais_alerta).where(
                PreferenciasUsuario.usuario_id == usuario_id
            )
        )
    ).scalar_one_or_none()
    return [c for c in (pref or []) if c in CANAIS_DA_CONTA]


async def definir_preferidos(
    session: AsyncSession, usuario_id: uuid.UUID, canais: list[str]
) -> list[str]:
    limpos = sorted({c for c in canais if c in CANAIS_DA_CONTA})
    stmt = pg_insert(PreferenciasUsuario).values(usuario_id=usuario_id, canais_alerta=limpos)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["usuario_id"], set_={"canais_alerta": stmt.excluded.canais_alerta}
        )
    )
    return limpos


async def inscricoes(session: AsyncSession, usuario_id: uuid.UUID) -> list[PushInscricao]:
    return list(
        (await session.execute(select(PushInscricao).where(PushInscricao.usuario_id == usuario_id)))
        .scalars()
        .all()
    )


async def da_conta(session: AsyncSession, usuario: Usuario) -> set[str]:
    """Os canais que a CONTA liga para todo alerta, além do painel."""
    canais = set(await preferidos(session, usuario.id))
    if usuario.optin_wpp and usuario.telefone_wpp:
        canais.add("wpp")
    if await inscricoes(session, usuario.id):
        canais.add("push")
    return canais


async def inscrever(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> None:
    stmt = pg_insert(PushInscricao).values(
        usuario_id=usuario_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=(user_agent or "")[:255] or None,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_push_inscricoes_usuario_endpoint",
            set_={
                "p256dh": stmt.excluded.p256dh,
                "auth": stmt.excluded.auth,
                "user_agent": stmt.excluded.user_agent,
                "ultimo_erro": None,
            },
        )
    )


async def cancelar(session: AsyncSession, usuario_id: uuid.UUID, endpoint: str) -> int:
    resultado = await session.execute(
        delete(PushInscricao).where(
            PushInscricao.usuario_id == usuario_id, PushInscricao.endpoint == endpoint
        )
    )
    return resultado.rowcount or 0


async def enviar_push(
    session: AsyncSession, usuario_id: uuid.UUID, mensagem: dict
) -> dict[str, int]:
    """Entrega a mensagem a TODOS os navegadores inscritos do usuário.

    Inscrição que o serviço de push deu como expirada (404/410) é apagada —
    senão toda varredura pagaria o mesmo erro para sempre. Outras falhas ficam
    em `ultimo_erro` (é o que o diagnóstico mostra) e não derrubam nada.
    """
    enviados = falhas = removidas = 0
    agora = datetime.now(UTC)
    for insc in await inscricoes(session, usuario_id):
        try:
            await webpush.enviar(insc.endpoint, insc.p256dh, insc.auth, mensagem)
            insc.ultimo_envio_em = agora
            insc.ultimo_erro = None
            enviados += 1
        except webpush.InscricaoExpirada:
            await session.delete(insc)
            removidas += 1
        except Exception as exc:  # noqa: BLE001 — canal best-effort
            insc.ultimo_erro = f"{type(exc).__name__}: {exc}"[:500]
            falhas += 1
            log.warning("web push falhou para %s", usuario_id, exc_info=True)
    return {"enviados": enviados, "falhas": falhas, "removidas": removidas}
