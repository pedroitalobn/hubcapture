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

from ...ai import chat as ai_chat
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...services import copiloto as copiloto_service
from ...services import rag
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Módulo desligável pelo painel admin: desativado → todo o eixo responde 404.
router = APIRouter(
    tags=["copiloto"], dependencies=[Depends(require_modulo("copiloto"))]
)


class ChatRequest(BaseModel):
    pergunta: str
    modo: str = "propostas"  # 'propostas' | 'copiloto'


@router.post("/copiloto/chat")
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

    papel = user.papel or "executivo"

    async def gen() -> AsyncIterator[str]:
        async for token in ai_chat.stream(contexto, body.pergunta, papel):
            yield f"data: {json.dumps({'delta': token}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
