"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import NATUREZAS_JURIDICAS, Proposta
from ..schemas.proposta import FiltrosPropostas, OpcaoFiltro, PropostaCanonica

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
    "natureza_juridica",
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "valor_total",
    "contrapartida",
    "situacao",
    "emenda",
    "prazos",
    "pendencias",
    "movimentacao",
    "data_atualizacao_fonte",
    "url_origem",
    "proveniencia",
    "hash_conteudo",
)


def _like(termo: str) -> str:
    """Padrão ILIKE 'contém', com os curingas do usuário escapados."""
    escapado = termo.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _filtros_where(
    stmt,
    *,
    numero: str | None,
    municipios: Sequence[str] | None,
    fonte: str | None,
    situacao: str | None,
    naturezas: Sequence[str] | None,
    valor_min: Decimal | None,
    valor_max: Decimal | None,
):
    """Aplica os filtros de busca do painel a um SELECT sobre `propostas`."""
    if numero and numero.strip():
        padrao = _like(numero)
        # o painel mostra `id_externo` como "Nº", e a numeração oficial mora em
        # `numero_proposta` — buscar nos dois (e na emenda) evita "não achei".
        stmt = stmt.where(
            or_(
                Proposta.numero_proposta.ilike(padrao, escape="\\"),
                Proposta.id_externo.ilike(padrao, escape="\\"),
                Proposta.emenda.ilike(padrao, escape="\\"),
            )
        )
    if municipios:
        stmt = stmt.where(Proposta.municipio_ibge.in_(list(municipios)))
    if fonte:
        stmt = stmt.where(Proposta.fonte == fonte)
    if situacao:
        stmt = stmt.where(Proposta.situacao == situacao)
    if naturezas:
        stmt = stmt.where(Proposta.natureza_juridica.in_(list(naturezas)))
    # range de valor: proposta sem valor informado fica de fora quando há corte
    if valor_min is not None:
        stmt = stmt.where(Proposta.valor_total >= valor_min)
    if valor_max is not None:
        stmt = stmt.where(Proposta.valor_total <= valor_max)
    return stmt


async def listar(
    session: AsyncSession,
    *,
    numero: str | None = None,
    municipios: Sequence[str] | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    naturezas_juridicas: Sequence[str] | None = None,
    valor_min: Decimal | None = None,
    valor_max: Decimal | None = None,
) -> list[Proposta]:
    stmt = _filtros_where(
        select(Proposta),
        numero=numero,
        municipios=municipios,
        fonte=fonte,
        situacao=situacao,
        naturezas=naturezas_juridicas,
        valor_min=valor_min,
        valor_max=valor_max,
    )
    stmt = stmt.order_by(Proposta.cache_atualizado_em.desc().nullslast())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _contagem(session: AsyncSession, coluna) -> list[tuple[str, int]]:
    """Agrupa por `coluna` contando propostas (já recortadas pelo RLS)."""
    stmt = (
        select(coluna, func.count(Proposta.id))
        .where(coluna.is_not(None))
        .group_by(coluna)
        .order_by(func.count(Proposta.id).desc())
    )
    return [(v, int(n)) for v, n in (await session.execute(stmt)).all()]


async def filtros(session: AsyncSession) -> FiltrosPropostas:
    """Opções de filtro derivadas do cache visível ao usuário (RLS)."""
    total, valor_min, valor_max = (
        await session.execute(
            select(
                func.count(Proposta.id),
                func.min(Proposta.valor_total),
                func.max(Proposta.valor_total),
            )
        )
    ).one()

    # município: agrupa pelo IBGE (chave canônica) e usa o nome/UF que houver
    municipios_stmt = (
        select(
            Proposta.municipio_ibge,
            func.max(Proposta.municipio_nome),
            func.max(Proposta.uf),
            func.count(Proposta.id),
        )
        .where(Proposta.municipio_ibge.is_not(None))
        .group_by(Proposta.municipio_ibge)
        .order_by(func.count(Proposta.id).desc())
    )
    municipios = [
        OpcaoFiltro(
            valor=ibge,
            label=f"{nome}{f'/{uf}' if uf else ''}" if nome else ibge,
            total=int(n),
        )
        for ibge, nome, uf, n in (await session.execute(municipios_stmt)).all()
    ]
    naturezas = [
        OpcaoFiltro(valor=slug, label=NATUREZAS_JURIDICAS.get(slug, slug), total=n)
        for slug, n in await _contagem(session, Proposta.natureza_juridica)
    ]
    fontes = [
        OpcaoFiltro(valor=f, label=f, total=n)
        for f, n in await _contagem(session, Proposta.fonte)
    ]
    situacoes = [
        OpcaoFiltro(valor=s, label=s, total=n)
        for s, n in await _contagem(session, Proposta.situacao)
    ]

    return FiltrosPropostas(
        total=int(total),
        municipios=municipios,
        naturezas_juridicas=naturezas,
        fontes=fontes,
        situacoes=situacoes,
        valor_min=valor_min,
        valor_max=valor_max,
    )


async def obter(session: AsyncSession, proposta_id: uuid.UUID) -> Proposta | None:
    result = await session.execute(select(Proposta).where(Proposta.id == proposta_id))
    return result.scalar_one_or_none()


async def upsert(session: AsyncSession, canonica: PropostaCanonica) -> None:
    """Insere/atualiza uma proposta pelo par único (fonte, id_externo)."""
    now = datetime.now(UTC)
    values = canonica.model_dump()
    values["cache_atualizado_em"] = now

    stmt = pg_insert(Proposta).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(
        constraint="uq_propostas_fonte_id_externo",
        set_=update_set,
    )
    await session.execute(stmt)
