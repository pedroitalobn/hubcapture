"""Job de alertas — a varredura de mudanças roda no CRON, não só no clique.

A detecção por critério (§53) já existia, mas só rodava quando alguém abria a
central de Alertas ou pedia "varrer agora". Ou seja: a coleta noturna trazia o
parecer novo, o empenho pago e a emenda aplicada, e o gestor só ficava sabendo
se entrasse no painel — exatamente o contrário do que um alerta serve.

Este job fecha o ciclo: logo depois do refresh diário atualizar o cache de um
usuário, a varredura DELE roda na sua própria sessão RLS e os alertas saem por
painel/e-mail/WhatsApp conforme os canais. Best-effort: um usuário que falha
não derruba o sweep.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from ..db.session import SessionLocal, rls_session
from ..models.usuario import Usuario
from ..services import oportunidades

log = logging.getLogger("hubcapture.jobs.alertas")


async def varrer_usuario(usuario_id: uuid.UUID) -> int:
    """Varredura de um usuário. Retorna quantos alertas foram criados."""
    async with rls_session(usuario_id) as session:
        usuario = (
            await session.execute(select(Usuario).where(Usuario.id == usuario_id))
        ).scalar_one_or_none()
        if usuario is None:
            return 0
        return await oportunidades.varredura(session, usuario)


async def _usuarios_ativos() -> list[uuid.UUID]:
    """Quem entra na varredura — a lista sai de `usuarios`, não das tabelas
    por-tenant.

    ATENÇÃO (pegadinha do RLS): `monitoramentos`/`favoritos` estão sob FORCE RLS
    e não têm policy de plataforma, então uma leitura sem tenant falha de duas
    maneiras — devolve ZERO linhas (foi o que fez o refresh diário girar em
    falso) ou estoura no cast, porque `set_config(..., true)` deixa a GUC do
    tenant como STRING VAZIA na conexão depois da transação e
    `current_setting('app.usuario_id')::uuid` não engole `''`. Justamente o
    estado da conexão logo depois de o sweep rodar as sessões RLS. `usuarios`
    está fora do RLS, então a listagem sai daí; quem decide se há algo a alertar
    é a própria varredura, já dentro do tenant.
    """
    async with SessionLocal() as session:
        stmt = select(Usuario.id).where(Usuario.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())


async def varrer_todos() -> dict:
    """Varre todos os usuários com acompanhamento. Resumo para log e teste."""
    alvos = await _usuarios_ativos()
    alertas = falhas = 0
    for usuario_id in alvos:
        try:
            alertas += await varrer_usuario(usuario_id)
        except Exception:  # noqa: BLE001 — um usuário não derruba o sweep
            falhas += 1
            log.warning("varredura de alertas falhou para %s", usuario_id, exc_info=True)
    log.info(
        "varredura de alertas: %d usuário(s), %d alerta(s), %d falha(s)",
        len(alvos),
        alertas,
        falhas,
    )
    return {"usuarios": len(alvos), "alertas": alertas, "falhas": falhas}
