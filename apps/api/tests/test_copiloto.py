"""Chat/Copiloto: fallback sem LLM, streaming e busca na base de conhecimento."""

from __future__ import annotations

from src.ai import chat
from src.db.session import SessionLocal
from src.models.base_conhecimento import BaseConhecimento
from src.services import copiloto


async def test_chat_responder_fallback_sem_llm() -> None:
    r = await chat.responder("CONTEXTO-XPTO", "quais propostas de saúde?")
    assert "IA indisponível" in r
    assert "CONTEXTO-XPTO" in r  # usa o contexto recuperado


async def test_chat_stream_fallback_sem_llm() -> None:
    chunks = [c async for c in chat.stream("CTX", "pergunta")]
    assert len(chunks) == 1
    assert "CTX" in chunks[0]


async def test_copiloto_busca_conhecimento() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            s.add(
                BaseConhecimento(
                    titulo="Como enviar proposta no TransfereGov",
                    conteudo="Passo a passo para cadastrar e enviar a proposta.",
                    categoria="tutorial",
                )
            )
        async with s.begin():
            itens = await copiloto.buscar_conhecimento(s, "enviar proposta")
            assert len(itens) == 1
            ctx = copiloto.montar_contexto(itens)
            assert "TransfereGov" in ctx
