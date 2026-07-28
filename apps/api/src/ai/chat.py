"""Chat com IA (LiteLLM) — geração a partir do contexto RAG.

Streaming para SSE. Provider/modelo/chave vêm do painel admin (config runtime).
Sem `llm_api_key`, degrada com elegância: devolve uma resposta baseada no contexto
recuperado (o Hub continua útil mesmo sem LLM).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..services import llm_providers

SYSTEM = (
    "Você é o assistente do Hub Capture, especialista em transferências e repasses "
    "do governo brasileiro. Responda de forma objetiva para um gestor público "
    "({papel}). Use SOMENTE o contexto fornecido; se não houver dado suficiente, diga."
)


def _mensagens(contexto: str, pergunta: str, papel: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM.format(papel=papel)},
        {"role": "user", "content": f"Contexto:\n{contexto}\n\nPergunta: {pergunta}"},
    ]


def _fallback(contexto: str) -> str:
    return (
        "IA indisponível (sem credencial configurada no painel). Com base no que "
        "encontrei no seu escopo:\n" + contexto
    )


async def responder(contexto: str, pergunta: str, papel: str = "executivo") -> str:
    params = await llm_providers.params_para("llm_model_chat", "claude-sonnet-5")
    if params is None:
        return _fallback(contexto)
    try:
        import litellm
    except ImportError:
        return _fallback(contexto)
    resp = await litellm.acompletion(**params, messages=_mensagens(contexto, pergunta, papel))
    return resp["choices"][0]["message"]["content"]


async def stream(contexto: str, pergunta: str, papel: str = "executivo") -> AsyncIterator[str]:
    params = await llm_providers.params_para("llm_model_chat", "claude-sonnet-5")
    if params is None:
        yield _fallback(contexto)
        return
    try:
        import litellm
    except ImportError:
        yield _fallback(contexto)
        return
    resposta = await litellm.acompletion(
        **params,
        messages=_mensagens(contexto, pergunta, papel),
        stream=True,
    )
    async for chunk in resposta:
        delta = chunk["choices"][0]["delta"].get("content")
        if delta:
            yield delta
