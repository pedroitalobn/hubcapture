"""Schemas do Class (help desk interno: artigos, módulos/aulas e hints)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Categorias ──────────────────────────────────────────────────────────────


class HelpCategoriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    slug: str
    descricao: str | None = None
    ordem: int = 0
    # contagem de artigos publicados — preenchida na listagem pública
    artigos: int = 0


class HelpCategoriaWrite(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = None
    ordem: int = 0


# ── Módulos (trilhas de aulas) ──────────────────────────────────────────────


class ModuloRef(BaseModel):
    """Referência curta do módulo dentro do artigo/aula."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str


class ClassModuloResumo(BaseModel):
    """Item de listagem de módulos (Class e admin)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str
    descricao: str | None = None
    publicado: bool
    ordem: int = 0
    # contagem de aulas — na visão pública, só as publicadas
    aulas: int = 0


class AulaResumo(BaseModel):
    """Uma aula na página do módulo (sem corpo — o link leva à aula)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str
    resumo: str | None = None
    ordem: int = 0
    publicado: bool
    videos: int = 0
    documentos: int = 0


class ClassModuloRead(BaseModel):
    """Módulo completo com as aulas em sequência."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str
    descricao: str | None = None
    publicado: bool
    ordem: int = 0
    aulas: list[AulaResumo] = []
    created_at: datetime
    updated_at: datetime | None = None


class ClassModuloCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    descricao: str | None = None
    publicado: bool = False
    ordem: int = 0


class ClassModuloPatch(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    descricao: str | None = None
    publicado: bool | None = None
    ordem: int | None = None


# ── Mídias (vídeos e documentos anexos) ─────────────────────────────────────


class HelpMidiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str  # 'video' | 'documento'
    titulo: str | None = None
    url: str | None = None  # vídeo externo (YouTube/Vimeo/mp4); None = upload
    orientacao: str = "horizontal"  # 'horizontal' | 'vertical'
    nome_arquivo: str | None = None
    mime: str | None = None
    tamanho: int | None = None
    ordem: int = 0


class HelpMidiaUrlCreate(BaseModel):
    """Mídia por URL (vídeo externo). Upload de arquivo vai por multipart."""

    tipo: str = Field(pattern="^(video|documento)$")
    url: str = Field(min_length=1)
    titulo: str | None = None
    orientacao: str = Field(default="horizontal", pattern="^(horizontal|vertical)$")
    ordem: int = 0


class HelpMidiaPatch(BaseModel):
    titulo: str | None = None
    orientacao: str | None = Field(default=None, pattern="^(horizontal|vertical)$")
    ordem: int | None = None


# ── Hints (chave de elemento de UI → artigo) ────────────────────────────────


class HintChaveCatalogo(BaseModel):
    """Uma chave plantável do catálogo (services/helpdesk.HINT_CHAVES)."""

    chave: str
    rotulo: str
    tela: str


class HintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chave: str
    artigo_id: uuid.UUID
    ativo: bool = True


class HintAdminRead(HintRead):
    """Visão do admin: hint + identidade do artigo apontado."""

    artigo_titulo: str
    artigo_slug: str
    artigo_publicado: bool


class HintSet(BaseModel):
    chave: str = Field(min_length=1, max_length=120)
    artigo_id: uuid.UUID
    ativo: bool = True


class HintPublico(BaseModel):
    """O que o painel precisa para desenhar o ícone ⓘ ao lado do elemento."""

    chave: str
    artigo_slug: str
    titulo: str
    resumo: str | None = None


# ── Artigos ─────────────────────────────────────────────────────────────────


class HelpArtigoResumo(BaseModel):
    """Item de listagem (Central de ajuda e admin) — sem o corpo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str
    resumo: str | None = None
    publicado: bool
    ordem: int = 0
    categoria: HelpCategoriaRead | None = None
    # preenchido = o artigo é uma AULA deste módulo
    modulo: ModuloRef | None = None
    # contagens para a listagem mostrar o que o artigo carrega
    videos: int = 0
    documentos: int = 0
    hints: int = 0
    updated_at: datetime | None = None


class HelpArtigoRead(BaseModel):
    """Artigo completo (página do artigo e editor do admin)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    slug: str
    resumo: str | None = None
    corpo: str
    publicado: bool
    ordem: int = 0
    categoria: HelpCategoriaRead | None = None
    modulo: ModuloRef | None = None
    midias: list[HelpMidiaRead] = []
    hints: list[HintRead] = []
    created_at: datetime
    updated_at: datetime | None = None


class HelpArtigoCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    resumo: str | None = None
    corpo: str = ""
    categoria_id: uuid.UUID | None = None
    # com módulo, o artigo nasce como AULA; `ordem` é a posição na sequência
    modulo_id: uuid.UUID | None = None
    publicado: bool = False
    ordem: int = 0


class HelpArtigoPatch(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    resumo: str | None = None
    corpo: str | None = None
    categoria_id: uuid.UUID | None = None
    modulo_id: uuid.UUID | None = None
    publicado: bool | None = None
    ordem: int | None = None
