"""Consultas de propostas salvas (as abas do construtor) — RLS por usuario_id.

A tela de Propostas é o CONSTRUTOR de consultas (§61): o gestor monta um
recorte, dá nome e ele vira uma aba. Cada aba é uma linha desta tabela, então
a consulta acompanha o usuário entre navegadores e máquinas — antes vivia em
`localStorage` e existia só naquele browser.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.consulta_proposta import ConsultaProposta
from ..schemas.consultas import ConsultaCreate, ConsultaUpdate, FiltrosConsulta

# Teto de abas por usuário. Não é regra de plano — é guarda contra a fileira
# virar um cinto de cem abas (que ninguém lê) por um laço no cliente.
MAX_CONSULTAS = 40

NOME_PADRAO = "Geral"


class LimiteConsultasExcedido(Exception):
    """Mais abas do que a fileira comporta."""


def _filtros_json(filtros: FiltrosConsulta) -> dict:
    # `mode="json"` porque o jsonb guarda Decimal/UUID como texto — sem isso o
    # asyncpg recusa o valor na hora de gravar.
    return filtros.model_dump(mode="json")


async def listar(session: AsyncSession, usuario_id: uuid.UUID) -> list[ConsultaProposta]:
    result = await session.execute(
        select(ConsultaProposta)
        .where(ConsultaProposta.usuario_id == usuario_id)
        .order_by(ConsultaProposta.ordem, ConsultaProposta.created_at)
    )
    return list(result.scalars().all())


async def obter(
    session: AsyncSession, usuario_id: uuid.UUID, consulta_id: uuid.UUID
) -> ConsultaProposta | None:
    result = await session.execute(
        select(ConsultaProposta).where(
            ConsultaProposta.id == consulta_id,
            ConsultaProposta.usuario_id == usuario_id,
        )
    )
    return result.scalar_one_or_none()


async def criar(
    session: AsyncSession, usuario_id: uuid.UUID, dados: ConsultaCreate
) -> ConsultaProposta:
    total = await session.scalar(
        select(func.count())
        .select_from(ConsultaProposta)
        .where(ConsultaProposta.usuario_id == usuario_id)
    )
    if (total or 0) >= MAX_CONSULTAS:
        raise LimiteConsultasExcedido
    proxima = await session.scalar(
        select(func.coalesce(func.max(ConsultaProposta.ordem), -1) + 1).where(
            ConsultaProposta.usuario_id == usuario_id
        )
    )
    consulta = ConsultaProposta(
        usuario_id=usuario_id,
        nome=dados.nome.strip(),
        filtros=_filtros_json(dados.filtros),
        ordem=int(proxima or 0),
    )
    session.add(consulta)
    await session.flush()
    return consulta


async def atualizar(
    session: AsyncSession, consulta: ConsultaProposta, dados: ConsultaUpdate
) -> ConsultaProposta:
    if dados.nome is not None:
        consulta.nome = dados.nome.strip()
    if dados.filtros is not None:
        consulta.filtros = _filtros_json(dados.filtros)
    if dados.ordem is not None:
        consulta.ordem = dados.ordem
    await session.flush()
    return consulta


async def remover(session: AsyncSession, consulta: ConsultaProposta) -> None:
    await session.execute(delete(ConsultaProposta).where(ConsultaProposta.id == consulta.id))


async def reordenar(
    session: AsyncSession, usuario_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[ConsultaProposta]:
    """Aplica a sequência recebida; o que não veio na lista vai para o fim.

    Reordenar não pode APAGAR aba: uma lista incompleta (aba criada noutra
    aba do navegador, chamada antiga) só reposiciona o que ela nomeia.
    """
    consultas = await listar(session, usuario_id)
    por_id = {c.id: c for c in consultas}
    posicao = 0
    for cid in ids:
        consulta = por_id.pop(cid, None)
        if consulta is None:
            continue
        consulta.ordem = posicao
        posicao += 1
    for consulta in por_id.values():  # os não citados preservam a ordem relativa
        consulta.ordem = posicao
        posicao += 1
    await session.flush()
    return await listar(session, usuario_id)


async def garantir_padrao(session: AsyncSession, usuario_id: uuid.UUID) -> list[ConsultaProposta]:
    """Lista as abas; sem nenhuma, cria a inicial vazia.

    A tela nunca abre sem aba — uma fileira vazia não diz ao gestor que ele
    precisa criar uma consulta, só parece quebrada.
    """
    consultas = await listar(session, usuario_id)
    if consultas:
        return consultas
    await criar(session, usuario_id, ConsultaCreate(nome=NOME_PADRAO))
    return await listar(session, usuario_id)
