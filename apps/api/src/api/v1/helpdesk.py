"""Central de ajuda (help desk interno) — leitura para qualquer usuário logado.

Três portas para o mesmo artigo: a página da Central, o link compartilhável
(`/panel/help/<slug>`) e o hint contextual (ícone ⓘ ao lado do elemento de UI
que o artigo explica). Conteúdo é nível-plataforma (sem tenant) e só o que
está PUBLICADO aparece aqui — rascunho vive apenas no admin.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.helpdesk import (
    HelpArtigoRead,
    HelpArtigoResumo,
    HelpCategoriaRead,
    HintPublico,
)
from ...services import helpdesk as service
from ...services.modulos import require_modulo
from ..deps import get_platform_db

# Módulo desligável pelo painel admin (§29): desligado → o eixo responde 404 e
# o front (que degrada sem o mapa de hints) simplesmente não desenha ícone.
router = APIRouter(tags=["help"], dependencies=[Depends(require_modulo("ajuda"))])


@router.get("/help/categories", response_model=list[HelpCategoriaRead])
async def listar_categorias(
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[HelpCategoriaRead]:
    itens = await service.listar_categorias_publicas(session)
    return [HelpCategoriaRead(**c) for c in itens]


@router.get("/help/articles", response_model=list[HelpArtigoResumo])
async def listar_artigos(
    categoria: str | None = Query(default=None, description="slug da categoria"),
    q: str | None = Query(default=None, description="busca livre (título/resumo/corpo)"),
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[HelpArtigoResumo]:
    artigos = await service.listar_artigos(
        session, somente_publicados=True, categoria_slug=categoria, q=q
    )
    return [HelpArtigoResumo.model_validate(service.resumo_de_artigo(a)) for a in artigos]


@router.get("/help/articles/{slug}", response_model=HelpArtigoRead)
async def obter_artigo(
    slug: str,
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> HelpArtigoRead:
    artigo = await service.artigo_por_slug(session, slug, somente_publicado=True)
    if artigo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ARTIGO_NAO_ENCONTRADO")
    return HelpArtigoRead.model_validate(artigo)


@router.get("/help/hints", response_model=list[HintPublico])
async def listar_hints(
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[HintPublico]:
    """Mapa chave→artigo que o painel carrega UMA vez para desenhar os ⓘ."""
    return [HintPublico(**h) for h in await service.hints_publicos(session)]


@router.get("/help/media/{midia_id}")
async def baixar_midia(
    midia_id: uuid.UUID,
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> Response:
    """Arquivo enviado pelo admin (vídeo/documento). Mídia por URL não passa aqui.

    O front busca autenticado (Bearer) e toca/baixa via object URL — a rota não
    precisa ser pública nem carregar token em query string.
    """
    midia = await service.midia_com_conteudo(session, midia_id)
    if midia is None or midia.conteudo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MIDIA_NAO_ENCONTRADA")
    nome = midia.nome_arquivo or f"midia-{midia.id}"
    return Response(
        content=midia.conteudo,
        media_type=midia.mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{nome}"',
            # conteúdo de ajuda muda raramente; o navegador pode segurar o vídeo
            "Cache-Control": "private, max-age=3600",
        },
    )
