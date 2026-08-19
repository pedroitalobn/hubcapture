"""Administração do Class (help desk interno) — só superuser.

O admin cria categorias, artigos e MÓDULOS de aprendizagem (trilhas que
ordenam AULAS — aula é um artigo com `modulo_id`), anexa mídias — vídeo por
URL (YouTube/Vimeo/mp4) ou ARQUIVO enviado (bytea; o container é efêmero,
disco local não é storage) — e planta HINTS: vincula o artigo a uma chave do
catálogo (`services/helpdesk.HINT_CHAVES`), fazendo o ícone ⓘ aparecer ao
lado daquele elemento no painel (ex.: a variável "Empenhado" da proposta).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_superuser
from ...models.helpdesk import (
    HelpdeskArtigo,
    HelpdeskCategoria,
    HelpdeskHint,
    HelpdeskMidia,
    HelpdeskModulo,
)
from ...schemas.helpdesk import (
    ClassModuloCreate,
    ClassModuloPatch,
    ClassModuloRead,
    ClassModuloResumo,
    HelpArtigoCreate,
    HelpArtigoPatch,
    HelpArtigoRead,
    HelpArtigoResumo,
    HelpCategoriaRead,
    HelpCategoriaWrite,
    HelpMidiaPatch,
    HelpMidiaRead,
    HelpMidiaUrlCreate,
    HintAdminRead,
    HintChaveCatalogo,
    HintSet,
)
from ...services import helpdesk as service
from ..deps import get_platform_db

router = APIRouter(tags=["admin-class"], dependencies=[Depends(current_superuser)])


async def _artigo_ou_404(session: AsyncSession, artigo_id: uuid.UUID) -> HelpdeskArtigo:
    artigo = (
        (await session.execute(select(HelpdeskArtigo).where(HelpdeskArtigo.id == artigo_id)))
        .scalars()
        .unique()
        .one_or_none()
    )
    if artigo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ARTIGO_NAO_ENCONTRADO")
    return artigo


# ── Categorias ──────────────────────────────────────────────────────────────


@router.get("/admin/class/categories", response_model=list[HelpCategoriaRead])
async def listar_categorias(
    session: AsyncSession = Depends(get_platform_db),
) -> list[HelpCategoriaRead]:
    return [HelpCategoriaRead(**c) for c in await service.listar_categorias_publicas(session)]


@router.post(
    "/admin/class/categories",
    response_model=HelpCategoriaRead,
    status_code=status.HTTP_201_CREATED,
)
async def criar_categoria(
    body: HelpCategoriaWrite,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpCategoriaRead:
    slug = await service.slug_unico(session, HelpdeskCategoria, service.slugify(body.nome))
    cat = HelpdeskCategoria(nome=body.nome, slug=slug, descricao=body.descricao, ordem=body.ordem)
    session.add(cat)
    await session.flush()
    return HelpCategoriaRead.model_validate(cat)


@router.patch("/admin/class/categories/{categoria_id}", response_model=HelpCategoriaRead)
async def editar_categoria(
    categoria_id: uuid.UUID,
    body: HelpCategoriaWrite,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpCategoriaRead:
    cat = await session.get(HelpdeskCategoria, categoria_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CATEGORIA_NAO_ENCONTRADA")
    if body.nome != cat.nome:
        cat.slug = await service.slug_unico(
            session, HelpdeskCategoria, service.slugify(body.nome), ignorar_id=cat.id
        )
    cat.nome = body.nome
    cat.descricao = body.descricao
    cat.ordem = body.ordem
    await session.flush()
    return HelpCategoriaRead.model_validate(cat)


@router.delete("/admin/class/categories/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_categoria(
    categoria_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    # artigos da categoria ficam "sem categoria" (FK é SET NULL) — nada some
    await session.execute(delete(HelpdeskCategoria).where(HelpdeskCategoria.id == categoria_id))


# ── Módulos (trilhas de aulas) ──────────────────────────────────────────────


async def _modulo_ou_404(session: AsyncSession, modulo_id: uuid.UUID) -> HelpdeskModulo:
    modulo = await session.get(HelpdeskModulo, modulo_id)
    if modulo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MODULO_NAO_ENCONTRADO")
    return modulo


@router.get("/admin/class/modules", response_model=list[ClassModuloResumo])
async def listar_modulos(
    session: AsyncSession = Depends(get_platform_db),
) -> list[ClassModuloResumo]:
    """Todos os módulos, inclusive rascunhos, com contagem total de aulas."""
    return [
        ClassModuloResumo(**m)
        for m in await service.listar_modulos(session, somente_publicados=False)
    ]


@router.post(
    "/admin/class/modules", response_model=ClassModuloRead, status_code=status.HTTP_201_CREATED
)
async def criar_modulo(
    body: ClassModuloCreate,
    session: AsyncSession = Depends(get_platform_db),
) -> ClassModuloRead:
    slug = await service.slug_unico(session, HelpdeskModulo, service.slugify(body.titulo))
    modulo = HelpdeskModulo(
        titulo=body.titulo,
        slug=slug,
        descricao=body.descricao,
        publicado=body.publicado,
        ordem=body.ordem,
    )
    session.add(modulo)
    await session.flush()
    completo = await service.modulo_por_slug(session, modulo.slug, somente_publicado=False)
    return ClassModuloRead(**completo)  # type: ignore[arg-type]


@router.get("/admin/class/modules/{modulo_id}", response_model=ClassModuloRead)
async def obter_modulo(
    modulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> ClassModuloRead:
    """Módulo com TODAS as aulas (inclusive rascunhos) — a visão do editor."""
    modulo = await _modulo_ou_404(session, modulo_id)
    completo = await service.modulo_por_slug(session, modulo.slug, somente_publicado=False)
    return ClassModuloRead(**completo)  # type: ignore[arg-type]


@router.patch("/admin/class/modules/{modulo_id}", response_model=ClassModuloRead)
async def editar_modulo(
    modulo_id: uuid.UUID,
    body: ClassModuloPatch,
    session: AsyncSession = Depends(get_platform_db),
) -> ClassModuloRead:
    modulo = await _modulo_ou_404(session, modulo_id)
    campos = body.model_dump(exclude_unset=True)
    if "titulo" in campos and campos["titulo"] != modulo.titulo:
        modulo.slug = await service.slug_unico(
            session, HelpdeskModulo, service.slugify(campos["titulo"]), ignorar_id=modulo.id
        )
    for campo, valor in campos.items():
        setattr(modulo, campo, valor)
    await session.flush()
    completo = await service.modulo_por_slug(session, modulo.slug, somente_publicado=False)
    return ClassModuloRead(**completo)  # type: ignore[arg-type]


@router.delete("/admin/class/modules/{modulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_modulo(
    modulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    # aulas NÃO somem: a FK é SET NULL e elas voltam a ser artigos avulsos
    await session.execute(delete(HelpdeskModulo).where(HelpdeskModulo.id == modulo_id))


# ── Artigos ─────────────────────────────────────────────────────────────────


@router.get("/admin/class/articles", response_model=list[HelpArtigoResumo])
async def listar_artigos(
    session: AsyncSession = Depends(get_platform_db),
) -> list[HelpArtigoResumo]:
    """Todos os artigos, inclusive rascunhos (a visão pública filtra publicado)."""
    artigos = await service.listar_artigos(session, somente_publicados=False)
    return [HelpArtigoResumo.model_validate(service.resumo_de_artigo(a)) for a in artigos]


@router.post(
    "/admin/class/articles", response_model=HelpArtigoRead, status_code=status.HTTP_201_CREATED
)
async def criar_artigo(
    body: HelpArtigoCreate,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpArtigoRead:
    slug = await service.slug_unico(session, HelpdeskArtigo, service.slugify(body.titulo))
    artigo = HelpdeskArtigo(
        titulo=body.titulo,
        slug=slug,
        resumo=body.resumo,
        corpo=body.corpo,
        categoria_id=body.categoria_id,
        modulo_id=body.modulo_id,
        publicado=body.publicado,
        ordem=body.ordem,
    )
    session.add(artigo)
    await session.flush()
    return HelpArtigoRead.model_validate(await _artigo_ou_404(session, artigo.id))


@router.get("/admin/class/articles/{artigo_id}", response_model=HelpArtigoRead)
async def obter_artigo(
    artigo_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpArtigoRead:
    return HelpArtigoRead.model_validate(await _artigo_ou_404(session, artigo_id))


@router.patch("/admin/class/articles/{artigo_id}", response_model=HelpArtigoRead)
async def editar_artigo(
    artigo_id: uuid.UUID,
    body: HelpArtigoPatch,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpArtigoRead:
    artigo = await _artigo_ou_404(session, artigo_id)
    campos = body.model_dump(exclude_unset=True)
    if "titulo" in campos and campos["titulo"] != artigo.titulo:
        # título novo → slug novo (o link antigo morre; o admin está editando
        # conscientemente). Colisão é resolvida com sufixo numérico.
        artigo.slug = await service.slug_unico(
            session, HelpdeskArtigo, service.slugify(campos["titulo"]), ignorar_id=artigo.id
        )
    for campo, valor in campos.items():
        setattr(artigo, campo, valor)
    await session.flush()
    # `refresh` porque trocar `categoria_id`/`modulo_id` NÃO atualiza os
    # relacionamentos já carregados: sem ele a resposta devolve a categoria e o
    # módulo ANTIGOS e o editor, que se repinta com o que volta daqui, mostra
    # que nada mudou — a aula recém-vinculada aparece como artigo avulso.
    await session.refresh(artigo)
    return HelpArtigoRead.model_validate(artigo)


@router.delete("/admin/class/articles/{artigo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_artigo(
    artigo_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    # mídias e hints caem junto (FK CASCADE)
    await session.execute(delete(HelpdeskArtigo).where(HelpdeskArtigo.id == artigo_id))


# ── Mídias (vídeo por URL ou arquivo; documento anexo) ──────────────────────


@router.post(
    "/admin/class/articles/{artigo_id}/media",
    response_model=HelpMidiaRead,
    status_code=status.HTTP_201_CREATED,
)
async def criar_midia_url(
    artigo_id: uuid.UUID,
    body: HelpMidiaUrlCreate,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpMidiaRead:
    """Mídia por URL — vídeo externo (YouTube/Vimeo/mp4 hospedado)."""
    await _artigo_ou_404(session, artigo_id)
    midia = HelpdeskMidia(
        artigo_id=artigo_id,
        tipo=body.tipo,
        titulo=body.titulo,
        url=body.url,
        orientacao=body.orientacao,
        ordem=body.ordem,
    )
    session.add(midia)
    await session.flush()
    return HelpMidiaRead.model_validate(midia)


@router.post(
    "/admin/class/articles/{artigo_id}/media/upload",
    response_model=HelpMidiaRead,
    status_code=status.HTTP_201_CREATED,
)
async def enviar_midia_arquivo(
    artigo_id: uuid.UUID,
    arquivo: UploadFile = File(...),
    tipo: str = Form(default="documento", pattern="^(video|documento)$"),
    titulo: str | None = Form(default=None),
    orientacao: str = Form(default="horizontal", pattern="^(horizontal|vertical)$"),
    session: AsyncSession = Depends(get_platform_db),
) -> HelpMidiaRead:
    """Upload de arquivo (vídeo curto ou documento). Vídeo pesado vai por URL."""
    await _artigo_ou_404(session, artigo_id)
    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ARQUIVO_VAZIO")
    if len(conteudo) > service.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"ARQUIVO_GRANDE_DEMAIS: máx {service.MAX_UPLOAD_BYTES // (1024 * 1024)}MB — "
            "para vídeo longo, anexe por URL (YouTube/Vimeo/mp4 hospedado)",
        )
    midia = HelpdeskMidia(
        artigo_id=artigo_id,
        tipo=tipo,
        titulo=titulo,
        orientacao=orientacao,
        nome_arquivo=arquivo.filename,
        mime=arquivo.content_type,
        tamanho=len(conteudo),
        conteudo=conteudo,
    )
    session.add(midia)
    await session.flush()
    return HelpMidiaRead.model_validate(midia)


@router.patch("/admin/class/media/{midia_id}", response_model=HelpMidiaRead)
async def editar_midia(
    midia_id: uuid.UUID,
    body: HelpMidiaPatch,
    session: AsyncSession = Depends(get_platform_db),
) -> HelpMidiaRead:
    midia = await session.get(HelpdeskMidia, midia_id)
    if midia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MIDIA_NAO_ENCONTRADA")
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(midia, campo, valor)
    await session.flush()
    return HelpMidiaRead.model_validate(midia)


@router.delete("/admin/class/media/{midia_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_midia(
    midia_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    await session.execute(delete(HelpdeskMidia).where(HelpdeskMidia.id == midia_id))


# ── Hints (chave de elemento de UI → artigo) ────────────────────────────────


@router.get("/admin/class/hint-keys", response_model=list[HintChaveCatalogo])
async def listar_chaves_de_hint() -> list[HintChaveCatalogo]:
    """Catálogo das chaves plantáveis — onde o ícone ⓘ pode aparecer no painel."""
    return [HintChaveCatalogo(**c) for c in service.HINT_CHAVES]


@router.get("/admin/class/hints", response_model=list[HintAdminRead])
async def listar_hints(
    session: AsyncSession = Depends(get_platform_db),
) -> list[HintAdminRead]:
    stmt = (
        select(HelpdeskHint, HelpdeskArtigo)
        .join(HelpdeskArtigo, HelpdeskHint.artigo_id == HelpdeskArtigo.id)
        .order_by(HelpdeskHint.chave)
    )
    rows = (await session.execute(stmt)).unique().all()
    return [
        HintAdminRead(
            id=hint.id,
            chave=hint.chave,
            artigo_id=hint.artigo_id,
            ativo=hint.ativo,
            artigo_titulo=artigo.titulo,
            artigo_slug=artigo.slug,
            artigo_publicado=artigo.publicado,
        )
        for hint, artigo in rows
    ]


@router.put("/admin/class/hints", response_model=list[HintAdminRead])
async def definir_hint(
    body: HintSet,
    session: AsyncSession = Depends(get_platform_db),
) -> list[HintAdminRead]:
    """Planta (ou realoca) o hint: a chave passa a apontar para este artigo."""
    if not service.chave_valida(body.chave):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"CHAVE_DESCONHECIDA: {body.chave}")
    await _artigo_ou_404(session, body.artigo_id)
    stmt = (
        pg_insert(HelpdeskHint)
        .values(chave=body.chave, artigo_id=body.artigo_id, ativo=body.ativo)
        .on_conflict_do_update(
            index_elements=["chave"],
            set_={"artigo_id": body.artigo_id, "ativo": body.ativo},
        )
    )
    await session.execute(stmt)
    return await listar_hints(session)


@router.delete("/admin/class/hints/{chave}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_hint(
    chave: str,
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    await session.execute(delete(HelpdeskHint).where(HelpdeskHint.chave == chave))
