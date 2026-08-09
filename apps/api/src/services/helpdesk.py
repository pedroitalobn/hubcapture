"""Central de ajuda interna — consultas e o CATÁLOGO de chaves de hint.

O help desk tem três portas de entrada para o mesmo artigo:
1. a página da Central de ajuda (`/panel/help`);
2. o link compartilhável (`/panel/help/<slug>`);
3. o HINT contextual — o ícone ⓘ ao lado do elemento de UI que o artigo
   explica (ex.: a variável "Empenhado" no detalhe da proposta).

O catálogo abaixo é a fonte de verdade das chaves plantáveis: o admin escolhe
uma chave ao vincular um artigo, e o front desenha o ícone onde houver
`<Hint chave="..."/>` com hint ativo. Adicionar um ponto novo de hint = uma
entrada aqui + um `<Hint/>` na tela correspondente.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ..models.helpdesk import HelpdeskArtigo, HelpdeskCategoria, HelpdeskHint, HelpdeskMidia

# ── Catálogo de chaves de hint ──────────────────────────────────────────────
# chave → (rótulo do dado, tela onde o ícone aparece). A chave é estável
# (contrato com o front); o rótulo é só para o admin escolher sem decorar.

HINT_CHAVES: list[dict[str, str]] = [
    # Detalhe da proposta — os dados que mais geram dúvida de vocabulário
    {"chave": "proposta.valor_total", "rotulo": "Valor total", "tela": "Detalhe da proposta"},
    {"chave": "proposta.contrapartida", "rotulo": "Contrapartida", "tela": "Detalhe da proposta"},
    {"chave": "proposta.empenhado", "rotulo": "Empenhado", "tela": "Detalhe da proposta"},
    {"chave": "proposta.prazo", "rotulo": "Próximo prazo", "tela": "Detalhe da proposta"},
    {"chave": "proposta.situacao", "rotulo": "Situação", "tela": "Detalhe da proposta"},
    {"chave": "proposta.pendencias", "rotulo": "Pendências", "tela": "Detalhe da proposta"},
    {"chave": "proposta.modalidade", "rotulo": "Modalidade", "tela": "Detalhe da proposta"},
    {
        "chave": "proposta.execucao",
        "rotulo": "Execução financeira (empenhado, liberado, pago)",
        "tela": "Detalhe da proposta",
    },
    {
        "chave": "proposta.numero_proposta",
        "rotulo": "Nº da proposta",
        "tela": "Detalhe da proposta",
    },
    {
        "chave": "proposta.plano_trabalho",
        "rotulo": "Plano de trabalho e pareceres",
        "tela": "Detalhe da proposta",
    },
    {
        "chave": "proposta.natureza_juridica",
        "rotulo": "Natureza jurídica",
        "tela": "Detalhe da proposta",
    },
    {"chave": "proposta.emenda", "rotulo": "Emenda parlamentar", "tela": "Detalhe da proposta"},
    # Captação (lista)
    {
        "chave": "funding.tipo",
        "rotulo": "Cadastrada × disponível",
        "tela": "Captação",
    },
    {"chave": "funding.fonte", "rotulo": "Fontes de captação", "tela": "Captação"},
    {
        "chave": "funding.qualificacao",
        "rotulo": "Tipo de transferência",
        "tela": "Captação",
    },
    # Recursos recebidos
    {
        "chave": "transfers.natureza",
        "rotulo": "Crédito × dedução (FPM)",
        "tela": "Recursos recebidos",
    },
    {
        "chave": "transfers.emendas",
        "rotulo": "Emendas parlamentares",
        "tela": "Recursos recebidos",
    },
    # Conformidade fiscal
    {"chave": "compliance.cauc", "rotulo": "CAUC", "tela": "Conformidade fiscal"},
    {"chave": "compliance.capag", "rotulo": "CAPAG", "tela": "Conformidade fiscal"},
    # Obras
    {"chave": "works.percentual", "rotulo": "Percentual de execução", "tela": "Obras"},
]

_CHAVES_VALIDAS = {c["chave"] for c in HINT_CHAVES}

# Upload em bytea: teto para não estourar request/banco. Vídeo maior que isso
# vai por URL (YouTube/Vimeo/mp4 hospedado) — a mensagem de erro orienta.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def chave_valida(chave: str) -> bool:
    return chave in _CHAVES_VALIDAS


def slugify(texto: str) -> str:
    """Slug estável para o link compartilhável (sem acento, minúsculo, hífens)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return limpo or "artigo"


async def slug_unico(
    session: AsyncSession,
    modelo: type[HelpdeskArtigo] | type[HelpdeskCategoria],
    base: str,
    ignorar_id: uuid.UUID | None = None,
) -> str:
    """`base`, `base-2`, `base-3`… até não colidir (títulos repetidos existem)."""
    candidato = base
    n = 1
    while True:
        stmt = select(modelo.id).where(modelo.slug == candidato)
        if ignorar_id is not None:
            stmt = stmt.where(modelo.id != ignorar_id)
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            return candidato
        n += 1
        candidato = f"{base}-{n}"


# ── Consultas públicas (qualquer usuário logado) ────────────────────────────


async def listar_categorias_publicas(session: AsyncSession) -> list[dict]:
    """Categorias com a contagem de artigos PUBLICADOS (vazia fica de fora)."""
    stmt = (
        select(HelpdeskCategoria, func.count(HelpdeskArtigo.id))
        .join(
            HelpdeskArtigo,
            (HelpdeskArtigo.categoria_id == HelpdeskCategoria.id)
            & (HelpdeskArtigo.publicado.is_(True)),
            isouter=True,
        )
        .group_by(HelpdeskCategoria.id)
        .order_by(HelpdeskCategoria.ordem, HelpdeskCategoria.nome)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": cat.id,
            "nome": cat.nome,
            "slug": cat.slug,
            "descricao": cat.descricao,
            "ordem": cat.ordem,
            "artigos": int(total),
        }
        for cat, total in rows
    ]


async def listar_artigos(
    session: AsyncSession,
    *,
    somente_publicados: bool = True,
    categoria_slug: str | None = None,
    q: str | None = None,
) -> list[HelpdeskArtigo]:
    stmt = select(HelpdeskArtigo).order_by(HelpdeskArtigo.ordem, HelpdeskArtigo.titulo)
    if somente_publicados:
        stmt = stmt.where(HelpdeskArtigo.publicado.is_(True))
    if categoria_slug:
        stmt = stmt.join(HelpdeskCategoria).where(HelpdeskCategoria.slug == categoria_slug)
    if q:
        padrao = f"%{q.strip()}%"
        stmt = stmt.where(
            HelpdeskArtigo.titulo.ilike(padrao)
            | HelpdeskArtigo.resumo.ilike(padrao)
            | HelpdeskArtigo.corpo.ilike(padrao)
        )
    return list((await session.execute(stmt)).scalars().unique())


async def artigo_por_slug(
    session: AsyncSession, slug: str, *, somente_publicado: bool = True
) -> HelpdeskArtigo | None:
    stmt = select(HelpdeskArtigo).where(HelpdeskArtigo.slug == slug)
    if somente_publicado:
        stmt = stmt.where(HelpdeskArtigo.publicado.is_(True))
    return (await session.execute(stmt)).scalars().unique().one_or_none()


async def hints_publicos(session: AsyncSession) -> list[dict]:
    """Mapa chave→artigo que o painel busca UMA vez para desenhar os ícones.

    Só hints ativos apontando para artigo PUBLICADO — rascunho não vira ícone.
    """
    stmt = (
        select(
            HelpdeskHint.chave,
            HelpdeskArtigo.slug,
            HelpdeskArtigo.titulo,
            HelpdeskArtigo.resumo,
        )
        .join(HelpdeskArtigo, HelpdeskHint.artigo_id == HelpdeskArtigo.id)
        .where(HelpdeskHint.ativo.is_(True), HelpdeskArtigo.publicado.is_(True))
        .order_by(HelpdeskHint.chave)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"chave": chave, "artigo_slug": slug, "titulo": titulo, "resumo": resumo}
        for chave, slug, titulo, resumo in rows
    ]


def resumo_de_artigo(artigo: HelpdeskArtigo) -> dict:
    """Projeção de listagem (sem corpo) com contagens de mídia/hints."""
    return {
        "id": artigo.id,
        "titulo": artigo.titulo,
        "slug": artigo.slug,
        "resumo": artigo.resumo,
        "publicado": artigo.publicado,
        "ordem": artigo.ordem,
        "categoria": artigo.categoria,
        "videos": sum(1 for m in artigo.midias if m.tipo == "video"),
        "documentos": sum(1 for m in artigo.midias if m.tipo == "documento"),
        "hints": len(artigo.hints),
        "updated_at": artigo.updated_at,
    }


async def midia_com_conteudo(session: AsyncSession, midia_id: uuid.UUID) -> HelpdeskMidia | None:
    """Mídia com o blob carregado (a coluna é deferred nas demais consultas)."""
    stmt = (
        select(HelpdeskMidia)
        .options(undefer(HelpdeskMidia.conteudo))
        .where(HelpdeskMidia.id == midia_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
