"""Monitoramentos — proposta-chave e busca de futuras propostas. RLS por usuario_id.

Favoritar TAMBÉM é acompanhar (§53): a favorita ganha um monitoramento de
`origem='favorito'`, com os critérios padrão, para que a coleta do cron que
mexer nela já gere alerta. O gestor pode afinar os critérios (ou parar) na
central de Alertas, como em qualquer outro monitoramento.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.favorito import Favorito
from ..models.monitoramento import Monitoramento, MonitoramentoBusca
from ..models.proposta import Proposta
from . import criterios_alerta, detect_changes


async def listar(
    session: AsyncSession, usuario_id: uuid.UUID, apenas_ativos: bool = False
) -> list[Monitoramento]:
    stmt = select(Monitoramento).where(Monitoramento.usuario_id == usuario_id)
    if apenas_ativos:
        stmt = stmt.where(Monitoramento.ativo.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def criar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    proposta_id: uuid.UUID,
    canais: list[str],
    criterios: list[str] | None = None,
    origem: str = "manual",
) -> Monitoramento:
    """Cria OU reconfigura o monitoramento (o POST é upsert: reenviar com
    outros critérios é como o usuário edita a escolha do multi-select)."""
    stmt = (
        pg_insert(Monitoramento)
        .values(
            usuario_id=usuario_id,
            proposta_id=proposta_id,
            ativo=True,
            canais=canais,
            criterios=criterios,
            origem=origem,
        )
        .on_conflict_do_update(
            constraint="uq_monitoramentos_usuario_proposta",
            # a origem NÃO é sobrescrita: quem já acompanhava na mão continua
            # `manual` mesmo depois de favoritar
            set_={"ativo": True, "canais": canais, "criterios": criterios},
        )
        .returning(Monitoramento)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def _snapshot_inicial(session: AsyncSession, proposta_id: uuid.UUID) -> dict | None:
    """Fotografia da proposta no momento em que ela entra no acompanhamento.

    Sem ela, a primeira varredura só serviria de linha de base e a novidade
    coletada no meio do caminho passaria em branco. Só a proposta (pareceres,
    empenhos e emendas ficam de fora): o snapshot é PODADO pelos critérios na
    varredura, e campo ausente lá é tratado como base, não como zero.
    """
    proposta = (
        await session.execute(
            select(Proposta).where(Proposta.id == proposta_id, Proposta.excluido_em.is_(None))
        )
    ).scalar_one_or_none()
    if proposta is None:  # fora do território (RLS) — nada a fotografar
        return None
    return detect_changes.podar(
        detect_changes.snapshot(proposta),
        criterios_alerta.padroes(criterios_alerta.ESCOPO_PROPOSTA)
        - {"parecer", "parecer_novo", "empenho", "empenho_pago", "emenda"},
    )


async def acompanhar_favorita(
    session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID
) -> None:
    """Favoritou → acompanha. Não mexe em monitoramento que já existe (nem
    ressuscita o que o usuário parou de propósito): o ON CONFLICT é DO NOTHING."""
    await session.execute(
        pg_insert(Monitoramento)
        .values(
            usuario_id=usuario_id,
            proposta_id=proposta_id,
            ativo=True,
            canais=["painel"],
            criterios=None,  # padrões do registro
            origem="favorito",
            snapshot=await _snapshot_inicial(session, proposta_id),
        )
        .on_conflict_do_nothing(constraint="uq_monitoramentos_usuario_proposta")
    )


async def garantir_das_favoritas(session: AsyncSession, usuario_id: uuid.UUID) -> int:
    """Cobre as favoritas anteriores à feature (e qualquer uma que tenha
    escapado). Retorna quantos acompanhamentos foram criados."""
    faltando = (
        (
            await session.execute(
                select(Favorito.proposta_id)
                .outerjoin(
                    Monitoramento,
                    (Monitoramento.proposta_id == Favorito.proposta_id)
                    & (Monitoramento.usuario_id == Favorito.usuario_id),
                )
                .where(Favorito.usuario_id == usuario_id, Monitoramento.id.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for proposta_id in faltando:
        await acompanhar_favorita(session, usuario_id, proposta_id)
    return len(faltando)


async def desativar(
    session: AsyncSession, usuario_id: uuid.UUID, monitoramento_id: uuid.UUID
) -> None:
    await session.execute(
        update(Monitoramento)
        .where(
            Monitoramento.id == monitoramento_id,
            Monitoramento.usuario_id == usuario_id,
        )
        .values(ativo=False)
    )


# ── Busca de FUTURAS propostas (município + área/fonte) ─────────────────────
async def listar_buscas(session: AsyncSession, usuario_id: uuid.UUID) -> list[MonitoramentoBusca]:
    result = await session.execute(
        select(MonitoramentoBusca).where(MonitoramentoBusca.usuario_id == usuario_id)
    )
    return list(result.scalars().all())


async def criar_busca(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    *,
    municipio_ibge: str,
    area: str | None,
    fonte: str | None,
    canais: list[str],
    criterios: list[str] | None = None,
) -> MonitoramentoBusca:
    stmt = (
        pg_insert(MonitoramentoBusca)
        .values(
            usuario_id=usuario_id,
            municipio_ibge=municipio_ibge,
            area=area,
            fonte=fonte,
            ativo=True,
            canais=canais,
            criterios=criterios,
        )
        .on_conflict_do_update(
            constraint="uq_monitoramentos_busca_escopo",
            set_={"ativo": True, "canais": canais, "criterios": criterios},
        )
        .returning(MonitoramentoBusca)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def desativar_busca(
    session: AsyncSession, usuario_id: uuid.UUID, busca_id: uuid.UUID
) -> None:
    await session.execute(
        update(MonitoramentoBusca)
        .where(
            MonitoramentoBusca.id == busca_id,
            MonitoramentoBusca.usuario_id == usuario_id,
        )
        .values(ativo=False)
    )


async def esta_monitorando(
    session: AsyncSession, usuario_id: uuid.UUID, proposta_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(Monitoramento.id).where(
            Monitoramento.usuario_id == usuario_id,
            Monitoramento.proposta_id == proposta_id,
            Monitoramento.ativo.is_(True),
        )
    )
    return result.first() is not None
