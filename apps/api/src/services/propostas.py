"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.

Classificação por ano: usa SEMPRE `ano` (ano de criação na fonte). Ordenar ou
agrupar por `data_atualizacao_fonte`/`cache_atualizado_em` jogaria uma proposta
criada em 2022 para dentro de 2026 só porque teve movimentação recente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import Proposta
from ..schemas.proposta import AnoResumo, PropostaCanonica

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
    "ano",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
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
    "data_criacao_fonte",
    "data_atualizacao_fonte",
    "url_origem",
    "proveniencia",
    "hash_conteudo",
)


def _filtrar(
    stmt: Select,
    *,
    municipio: str | None,
    fonte: str | None,
    situacao: str | None,
    ano: int | None,
) -> Select:
    if municipio:
        stmt = stmt.where(Proposta.municipio_ibge == municipio)
    if fonte:
        stmt = stmt.where(Proposta.fonte == fonte)
    if situacao:
        stmt = stmt.where(Proposta.situacao == situacao)
    if ano is not None:
        stmt = stmt.where(Proposta.ano == ano)
    return stmt


async def listar(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    ano: int | None = None,
) -> list[Proposta]:
    stmt = _filtrar(
        select(Proposta),
        municipio=municipio,
        fonte=fonte,
        situacao=situacao,
        ano=ano,
    )
    # mais recentes primeiro pelo ANO DE CRIAÇÃO; atualização só desempata
    stmt = stmt.order_by(
        Proposta.ano.desc().nullslast(),
        Proposta.data_criacao_fonte.desc().nullslast(),
        Proposta.cache_atualizado_em.desc().nullslast(),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def anos(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
) -> list[AnoResumo]:
    """Classificação por ano de criação: quantidade e valor por safra."""
    stmt = _filtrar(
        select(
            Proposta.ano,
            func.count(Proposta.id),
            func.coalesce(func.sum(Proposta.valor_total), 0),
        ),
        municipio=municipio,
        fonte=fonte,
        situacao=situacao,
        ano=None,
    )
    stmt = stmt.group_by(Proposta.ano).order_by(Proposta.ano.desc().nullslast())
    rows = (await session.execute(stmt)).all()
    return [
        AnoResumo(ano=ano, total=int(total), valor_total=valor)
        for ano, total, valor in rows
    ]


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
