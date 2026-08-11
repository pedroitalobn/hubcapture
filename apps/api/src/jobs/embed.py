"""Job embed_new — gera embeddings das propostas ainda sem vetor.

Roda no pipeline pós-sync. Sem embeddings configurados, é no-op (retorna 0).
NOTA: o cron global multi-tenant deve rodar com role BYPASSRLS; aqui a sessão
segue o RLS (útil por-usuário e nos testes).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.embeddings import embed
from ..models.proposta import Proposta
from ..models.proposta_embedding import PropostaEmbedding


def _texto(p: Proposta) -> str:
    partes = [p.titulo, p.objeto, p.orgao_superior, p.situacao, p.municipio_nome]
    return " · ".join(x for x in partes if x)


async def embed_pendentes(session: AsyncSession, limite: int = 100) -> int:
    """Embeda as propostas sem embedding. Retorna quantas foram vetorizadas."""
    subq = select(PropostaEmbedding.proposta_id)
    stmt = (
        select(Proposta)
        .where(Proposta.id.notin_(subq), Proposta.excluido_em.is_(None))
        .limit(limite)
    )
    propostas = list((await session.execute(stmt)).scalars().all())
    if not propostas:
        return 0
    vetores = await embed([_texto(p) for p in propostas])
    if vetores is None:  # embeddings desabilitado
        return 0
    for p, v in zip(propostas, vetores, strict=False):
        await session.execute(
            pg_insert(PropostaEmbedding)
            .values(proposta_id=p.id, embedding=v)
            .on_conflict_do_update(index_elements=["proposta_id"], set_={"embedding": v})
        )
    return len(propostas)
