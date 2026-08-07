"""RAG — recuperação de propostas relevantes (pgvector) com RLS.

Embed a pergunta e busca por similaridade de cosseno em `proposta_embeddings`
(join com `propostas`); a RLS garante que só as propostas do usuário aparecem.
Sem embeddings configurados, cai para busca textual (ILIKE) — o chat continua útil.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.embeddings import embed_um
from ..models.proposta import Proposta
from ..models.proposta_embedding import PropostaEmbedding
from .municipios import rotulo


async def buscar_propostas(session: AsyncSession, query: str, k: int = 5) -> list[Proposta]:
    vec = await embed_um(query)
    if vec is not None:
        stmt = (
            select(Proposta)
            .join(PropostaEmbedding, PropostaEmbedding.proposta_id == Proposta.id)
            .order_by(PropostaEmbedding.embedding.cosine_distance(vec))
            .limit(k)
        )
    else:
        like = f"%{query}%"
        stmt = (
            select(Proposta)
            .where(or_(Proposta.titulo.ilike(like), Proposta.objeto.ilike(like)))
            .limit(k)
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def montar_contexto(propostas: list[Proposta]) -> str:
    """Serializa as propostas recuperadas como contexto para o LLM.

    Mesma hierarquia das telas (seção 23): o município (pelo nome) abre a linha,
    o empenho entra junto do valor e o identificador da fonte fecha — assim o
    modelo cita "São Paulo/SP" na resposta, não um código IBGE cru.
    """
    linhas = []
    for p in propostas:
        municipio = rotulo(p.municipio_nome, p.uf, p.municipio_ibge)
        empenhado = (p.execucao or {}).get("valor_empenhado") if p.execucao else None
        linhas.append(
            f"- {municipio} · {p.titulo or ''} · órgão: {p.orgao_superior or '—'}"
            f" · situação: {p.situacao or '—'} · valor: {p.valor_total or '—'}"
            f" · empenhado: {empenhado or '—'}"
            f" · id na fonte: {p.fonte}/{p.id_externo}"
        )
    return "\n".join(linhas) if linhas else "(nenhuma proposta encontrada no seu escopo)"
