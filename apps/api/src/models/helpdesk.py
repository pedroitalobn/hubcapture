"""Class (help desk interno): categorias, artigos, módulos/aulas, mídias e hints.

Nível-plataforma (sem RLS), como `base_conhecimento` — todo usuário logado lê
o que está publicado; só o admin escreve (guard `is_superuser` nos endpoints).
O hint é o diferencial: mapeia uma CHAVE de elemento de UI (catálogo em
`services/helpdesk.py`) para um artigo, e o front mostra o ícone ⓘ ao lado do
elemento (ex.: a variável "Empenhado" no detalhe da proposta).

Camada de curso: `HelpdeskModulo` agrupa AULAS em sequência. Aula NÃO é
entidade nova — é um artigo com `modulo_id` (reusa corpo, mídias, hints e o
link compartilhável); `ordem` é a posição da aula dentro do módulo.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ._mixins import created_at_col, updated_at_col, uuid_pk


class HelpdeskCategoria(Base):
    __tablename__ = "helpdesk_categorias"

    id: Mapped[uuid.UUID] = uuid_pk()
    nome: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()


class HelpdeskModulo(Base):
    """Módulo de aprendizagem — a "trilha" que ordena aulas (ex.: Captação 101)."""

    __tablename__ = "helpdesk_modulos"

    id: Mapped[uuid.UUID] = uuid_pk()
    titulo: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    publicado: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()

    aulas: Mapped[list[HelpdeskArtigo]] = relationship(
        lazy="selectin",
        order_by="(HelpdeskArtigo.ordem, HelpdeskArtigo.titulo)",
        back_populates="modulo",
    )


class HelpdeskArtigo(Base):
    __tablename__ = "helpdesk_artigos"

    id: Mapped[uuid.UUID] = uuid_pk()
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("helpdesk_categorias.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    # preenchido = este artigo é uma AULA do módulo; `ordem` é a posição nele.
    # SET NULL: excluir o módulo devolve as aulas ao acervo avulso, nada some.
    modulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("helpdesk_modulos.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    titulo: Mapped[str] = mapped_column(String(255))
    # slug é a identidade pública do artigo/aula (link compartilhável /panel/class/<slug>)
    slug: Mapped[str] = mapped_column(String(280), unique=True)
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    corpo: Mapped[str] = mapped_column(Text, server_default="")
    publicado: Mapped[bool] = mapped_column(Boolean, server_default="false", index=True)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()

    categoria: Mapped[HelpdeskCategoria | None] = relationship(lazy="selectin")
    modulo: Mapped[HelpdeskModulo | None] = relationship(lazy="selectin", back_populates="aulas")
    midias: Mapped[list[HelpdeskMidia]] = relationship(
        lazy="selectin",
        order_by="HelpdeskMidia.ordem",
        cascade="all, delete-orphan",
        back_populates="artigo",
    )
    hints: Mapped[list[HelpdeskHint]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="artigo"
    )


class HelpdeskMidia(Base):
    """Anexo do artigo: vídeo (URL externa ou arquivo) ou documento (arquivo).

    `conteudo` (bytea) guarda o upload — o container é efêmero, disco local não
    é storage. Vídeo pesado vai por `url` (YouTube/Vimeo/mp4 hospedado).
    """

    __tablename__ = "helpdesk_midias"

    id: Mapped[uuid.UUID] = uuid_pk()
    artigo_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("helpdesk_artigos.id", ondelete="CASCADE"),
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(16), server_default="documento")
    titulo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    orientacao: Mapped[str] = mapped_column(String(12), server_default="horizontal")
    nome_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tamanho: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = created_at_col()

    artigo: Mapped[HelpdeskArtigo] = relationship(back_populates="midias")


class HelpdeskHint(Base):
    """Chave de elemento de UI → artigo. Uma chave aponta para UM artigo."""

    __tablename__ = "helpdesk_hints"

    id: Mapped[uuid.UUID] = uuid_pk()
    chave: Mapped[str] = mapped_column(String(120), unique=True)
    artigo_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("helpdesk_artigos.id", ondelete="CASCADE"),
        index=True,
    )
    ativo: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at_col()

    artigo: Mapped[HelpdeskArtigo] = relationship(back_populates="hints")
