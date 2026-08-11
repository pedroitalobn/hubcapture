"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..ingestion import natureza_juridica as nj
from ..models.proposta import Proposta
from ..schemas.proposta import PropostaCanonica

# Coluna da natureza com fallback: linhas antigas (sem classificação) contam
# como 'outros', para que as duas lentes juntas cubram sempre a base inteira.
NATUREZA_COL = func.coalesce(Proposta.natureza_juridica, nj.OUTROS)

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
    "natureza_juridica",
    "natureza_juridica_descricao",
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
    natureza_juridica: str | None = None,
) -> list[Proposta]:
    stmt = select(Proposta)
    if municipio:
        stmt = stmt.where(Proposta.municipio_ibge == municipio)
    if fonte:
        stmt = stmt.where(Proposta.fonte == fonte)
    if situacao:
        stmt = stmt.where(Proposta.situacao == situacao)
    if natureza_juridica:
        stmt = stmt.where(NATUREZA_COL == natureza_juridica)
    stmt = stmt.order_by(Proposta.cache_atualizado_em.desc().nullslast())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def contar_por_natureza(session: AsyncSession) -> dict[str, int]:
    """Quantas propostas visíveis (RLS) há por natureza jurídica.

    Sempre devolve as duas lentes, mesmo zeradas — o painel mostra o filtro
    ainda que uma delas esteja vazia no território do usuário.
    """
    stmt = select(NATUREZA_COL.label("natureza"), func.count(Proposta.id)).group_by(
        NATUREZA_COL
    )
    contagem = dict.fromkeys(nj.NATUREZAS, 0)
    for natureza, total in (await session.execute(stmt)).all():
        contagem[natureza] = contagem.get(natureza, 0) + int(total)
    return contagem


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
