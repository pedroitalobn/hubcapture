"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import Proposta
from ..schemas.proposta import PropostaCanonica

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
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
    "data_atualizacao_fonte",
    "url_origem",
    "proveniencia",
    "hash_conteudo",
)


async def listar(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    numero: str | None = None,
) -> list[Proposta]:
    stmt = select(Proposta)
    if municipio:
        stmt = stmt.where(Proposta.municipio_ibge == municipio)
    if fonte:
        stmt = stmt.where(Proposta.fonte == fonte)
    if situacao:
        stmt = stmt.where(Proposta.situacao == situacao)
    if numero and numero.strip():
        # busca pelo número da proposta (NR_PROPOSTA). Casa também com o
        # id_externo porque nem toda fonte publica os dois separadamente.
        alvo = f"%{numero.strip()}%"
        stmt = stmt.where(
            or_(Proposta.numero_proposta.ilike(alvo), Proposta.id_externo.ilike(alvo))
        )
    stmt = stmt.order_by(Proposta.cache_atualizado_em.desc().nullslast())
    result = await session.execute(stmt)
    return list(result.scalars().all())


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
