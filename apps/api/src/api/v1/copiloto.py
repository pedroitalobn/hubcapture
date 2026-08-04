"""Chat do Copiloto (SSE) — RAG sobre as propostas do usuário ou base de conhecimento.

Streaming em text/event-stream. A recuperação (RAG) roda com a sessão RLS ANTES do
stream; o gerador só chama o LLM (não toca no banco). Sem LLM, degrada com o contexto.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...ai import agent as ai_agent
from ...ai import chat as ai_chat
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...services import copiloto as copiloto_service
from ...services import propostas as propostas_service
from ...services import rag
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin: desativado → todo o eixo responde 404.
router = APIRouter(
    tags=["copiloto"], dependencies=[Depends(require_modulo("copiloto"))]
)

# Perguntas sobre prazo ("quais propostas vencem este mês?") têm resposta
# estruturada — o RAG por similaridade não garante recall em datas, então a
# consulta ao jsonb `prazos` complementa o contexto.
_KW_PRAZO = ("venc", "prazo", "expira", "data limite", "data-limite")


async def _contexto_prazos(session: AsyncSession, pergunta: str) -> str:
    if not any(kw in pergunta.lower() for kw in _KW_PRAZO):
        return ""
    dias = 7 if "semana" in pergunta.lower() else 30
    com_prazo = await propostas_service.listar_por_prazo(session, dias=dias)
    if not com_prazo:
        return (
            f"\n\n[Consulta estruturada de prazos] Nenhuma proposta do território "
            f"tem prazo nos próximos {dias} dias."
        )
    linhas = []
    for p, prazos in com_prazo[:20]:
        datas = ", ".join(f"{pr.get('tipo') or 'prazo'}: {pr.get('data_limite')}" for pr in prazos)
        titulo = p.titulo or p.objeto or p.numero_proposta or p.id_externo
        linhas.append(f"- {titulo} ({p.fonte}, {p.municipio_nome or p.municipio_ibge}) → {datas}")
    return f"\n\n[Consulta estruturada de prazos — próximos {dias} dias]\n" + "\n".join(linhas)


class ChatRequest(BaseModel):
    pergunta: str
    modo: str = "propostas"  # 'propostas' | 'copiloto'


@router.post("/copilot/chat")
async def copiloto_chat(
    body: ChatRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> StreamingResponse:
    # recuperação (RAG) sob RLS — feito aqui, com a sessão aberta
    if body.modo == "copiloto":
        itens = await copiloto_service.buscar_conhecimento(session, body.pergunta)
        contexto = copiloto_service.montar_contexto(itens)
    else:
        propostas = await rag.buscar_propostas(session, body.pergunta)
        contexto = rag.montar_contexto(propostas)
        contexto += await _contexto_prazos(session, body.pergunta)

    papel = user.papel or "executivo"

    async def gen() -> AsyncIterator[str]:
        async for token in ai_chat.stream(contexto, body.pergunta, papel):
            yield f"data: {json.dumps({'delta': token}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


class IslandRequest(BaseModel):
    pergunta: str


@router.post("/copilot/island")
async def copiloto_island(
    body: IslandRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> StreamingResponse:
    """Agente do Dynamic Island (tool calling). O loop de ferramentas roda AQUI,
    com a sessão RLS do request viva; o stream só replaye os eventos coletados
    (mesma razão do RAG pré-stream acima)."""
    eventos = [e async for e in ai_agent.executar(session, user, body.pergunta)]

    async def gen() -> AsyncIterator[str]:
        for ev in eventos:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
