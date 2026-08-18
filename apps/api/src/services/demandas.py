"""Central de demandas da Assessoria — a fila de pedidos do gestor.

Ponto 20 do feedback. A Assessoria abria o WhatsApp e pronto: o pedido vivia na
conversa, sem estado e sem histórico, e ninguém sabia o que estava pendente.
Aqui a demanda é registro: nasce aberta, anda, e termina resolvida — com um
histórico que o gestor lê sem precisar rolar o zap.

Duas visões da MESMA tabela:
  - **do gestor** (`listar`/`criar`/`comentar`): sessão RLS, só as dele;
  - **da administração** (`listar_fila`/`responder`): sessão de plataforma, a
    fila inteira — é quem responde.

O histórico é jsonb append-only (`[{em, autor, texto, situacao}]`): a conversa
inteira num campo evita uma segunda tabela para o que sempre é lido junto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.demanda import SITUACOES, Demanda
from ..models.usuario import Usuario


class SituacaoInvalida(Exception):
    """Situação fora do ciclo de vida conhecido."""


class DemandaNaoEncontrada(Exception):
    """Não existe (ou não é do usuário — o RLS não deixa distinguir)."""


def validar_situacao(situacao: str) -> str:
    if situacao not in SITUACOES:
        raise SituacaoInvalida(situacao)
    return situacao


def _evento(autor: str, texto: str | None, situacao: str | None) -> dict:
    return {
        "em": datetime.now(UTC).isoformat(),
        "autor": autor,
        "texto": (texto or "").strip() or None,
        "situacao": situacao,
    }


async def criar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    *,
    assunto: str,
    descricao: str | None = None,
    municipio_ibge: str | None = None,
    proposta_id: uuid.UUID | None = None,
    origem: str = "painel",
) -> Demanda:
    demanda = Demanda(
        usuario_id=usuario_id,
        assunto=assunto.strip(),
        descricao=(descricao or "").strip() or None,
        municipio_ibge=municipio_ibge,
        proposta_id=proposta_id,
        situacao="aberta",
        origem=origem,
        historico=[_evento("gestor", descricao, "aberta")],
    )
    session.add(demanda)
    await session.flush()
    return demanda


async def listar(
    session: AsyncSession,
    *,
    situacao: str | None = None,
    incluir_resolvidas: bool = True,
) -> list[Demanda]:
    """As demandas do usuário da sessão (o RLS recorta), da mais nova à antiga."""
    stmt = select(Demanda).order_by(Demanda.created_at.desc())
    if situacao:
        stmt = stmt.where(Demanda.situacao == validar_situacao(situacao))
    elif not incluir_resolvidas:
        stmt = stmt.where(Demanda.situacao.notin_(("resolvida", "cancelada")))
    return list((await session.execute(stmt)).scalars().all())


async def obter(session: AsyncSession, demanda_id: uuid.UUID) -> Demanda:
    demanda = (
        await session.execute(select(Demanda).where(Demanda.id == demanda_id))
    ).scalar_one_or_none()
    if demanda is None:
        raise DemandaNaoEncontrada(str(demanda_id))
    return demanda


async def comentar(
    session: AsyncSession,
    demanda_id: uuid.UUID,
    *,
    texto: str,
    autor: str = "gestor",
    situacao: str | None = None,
) -> Demanda:
    """Acrescenta um evento ao histórico (e, opcionalmente, muda a situação)."""
    demanda = await obter(session, demanda_id)
    nova = validar_situacao(situacao) if situacao else None

    # `historico` é jsonb: mutar a lista no lugar não marca o atributo como
    # sujo no SQLAlchemy e o append se perderia no commit.
    demanda.historico = [*(demanda.historico or []), _evento(autor, texto, nova)]
    if nova:
        demanda.situacao = nova
        demanda.resolvida_em = datetime.now(UTC) if nova == "resolvida" else None
    await session.flush()
    return demanda


# ── Fila da administração (sessão de plataforma, sem RLS de tenant) ─────────


async def listar_fila(
    session: AsyncSession, *, situacao: str | None = None
) -> list[tuple[Demanda, Usuario | None]]:
    """A fila inteira com quem pediu — a administração precisa saber de quem é."""
    stmt = (
        select(Demanda, Usuario)
        .outerjoin(Usuario, Usuario.id == Demanda.usuario_id)
        .order_by(Demanda.created_at.desc())
    )
    if situacao:
        stmt = stmt.where(Demanda.situacao == validar_situacao(situacao))
    return [(d, u) for d, u in (await session.execute(stmt)).all()]


async def responder(
    session: AsyncSession,
    demanda_id: uuid.UUID,
    *,
    texto: str | None = None,
    situacao: str | None = None,
) -> Demanda:
    """Resposta da assessoria: entra no histórico como `assessoria`."""
    return await comentar(
        session, demanda_id, texto=texto or "", autor="assessoria", situacao=situacao
    )
