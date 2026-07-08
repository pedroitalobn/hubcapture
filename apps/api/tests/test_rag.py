"""RAG: busca por similaridade (pgvector) sob RLS + job de embeddings."""

from __future__ import annotations

from sqlalchemy import delete, func, select

from src.db.session import rls_session
from src.jobs import embed as embed_job
from src.models.municipio_interesse import MunicipioInteresse
from src.models.proposta import Proposta
from src.models.proposta_embedding import PropostaEmbedding
from src.services import rag

DIM = 1536


def _vec(pos: int) -> list[float]:
    return [1.0 if i == pos else 0.0 for i in range(DIM)]


async def _pid(session, fonte: str, ext: str):
    return (
        await session.execute(
            select(Proposta.id).where(Proposta.fonte == fonte, Proposta.id_externo == ext)
        )
    ).scalar_one()


async def test_rag_similaridade_respeita_rls(
    seed_user, seed_proposta, monkeypatch
) -> None:
    u = await seed_user("r@r.com")
    await seed_proposta("fns", "A", "3550308", "UBS Atenção Primária")
    await seed_proposta("fns", "B", "3550308", "Merenda escolar")
    await seed_proposta("fns", "C", "3304557", "UBS alheia")

    async def fake(_q):
        return _vec(0)

    monkeypatch.setattr(rag, "embed_um", fake)

    async with rls_session(u) as s:
        # usuário acompanha os dois municípios → enxerga A, B e C para semear
        s.add(MunicipioInteresse(usuario_id=u, ibge="3550308", modo="monitorado"))
        s.add(MunicipioInteresse(usuario_id=u, ibge="3304557", modo="monitorado"))
        await s.flush()
        for ext, pos in [("A", 0), ("B", 5), ("C", 0)]:
            s.add(PropostaEmbedding(proposta_id=await _pid(s, "fns", ext), embedding=_vec(pos)))
        await s.flush()
        # agora deixa de acompanhar o município de C → RLS deve escondê-lo
        await s.execute(
            delete(MunicipioInteresse).where(
                MunicipioInteresse.usuario_id == u,
                MunicipioInteresse.ibge == "3304557",
            )
        )
        achadas = await rag.buscar_propostas(s, "atenção primária", k=5)

    ids = [p.id_externo for p in achadas]
    assert "A" in ids
    assert "C" not in ids  # RLS esconde mesmo sendo o vetor mais próximo


async def test_rag_fallback_textual_sem_embeddings(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    u = await seed_user("t@t.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("fns", "A", "3550308", "Reforma da UBS central")

    async def fake(_q):
        return None  # embeddings desabilitado

    monkeypatch.setattr(rag, "embed_um", fake)
    async with rls_session(u) as s:
        achadas = await rag.buscar_propostas(s, "UBS", k=5)
    assert [p.id_externo for p in achadas] == ["A"]


async def test_embed_pendentes_popula(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    u = await seed_user("e@e.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("fns", "A", "3550308", "UBS")

    async def fake_embed(textos):
        return [_vec(0) for _ in textos]

    monkeypatch.setattr(embed_job, "embed", fake_embed)
    async with rls_session(u) as s:
        n = await embed_job.embed_pendentes(s)
        total = (
            await s.execute(select(func.count()).select_from(PropostaEmbedding))
        ).scalar_one()
    assert n == 1
    assert total == 1
