"""Marca (white label, §69) — a organização que veste o Hub com a própria identidade.

Nível-PLATAFORMA, sem RLS (como `planos`/`convites`): a marca é resolvida pelo
HOST antes de existir usuário (a tela de login já sai vestida), e o que ela
guarda — cores, logo, textos do login — é público por natureza. O isolamento de
DADOS continua onde sempre esteve: no RLS por `usuario_id`; pertencer a uma marca
não dá acesso a nada de outro usuário.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, updated_at_col, uuid_pk

# estados do domínio próprio (CNAME): pendente → verificado (DNS aponta para nós)
# → ativo (certificado/rota provisionados). `erro` guarda o motivo em
# `dominio_detalhe` — "o DNS não aponta" ≠ "o provisionamento falhou".
DOMINIO_STATUS = ("pendente", "verificado", "ativo", "erro")

# arquivos da marca: imagens e fontes. Bytes no banco (bytea), não em disco: o
# container é efêmero (mesma disciplina das mídias do Class, §37).
TIPOS_ASSET = ("logo", "logo_escuro", "icone", "login_imagem", "fonte_corpo", "fonte_titulo")


class Marca(Base):
    __tablename__ = "marcas"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    dono_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # plano atribuído a quem entra PELA marca (cadastro no host dela, convite dela)
    plano_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("planos.id", ondelete="SET NULL"), nullable=True
    )
    # cadastro aberto no host da marca vincula a conta nova a ela
    cadastro_aberto: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    dominio: Mapped[str | None] = mapped_column(String(253), unique=True, nullable=True)
    dominio_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dominio_detalhe: Mapped[str | None] = mapped_column(Text, nullable=True)
    dominio_verificado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # estado do provisionamento por HOST (subdomínio e domínio próprio):
    # {"marca.hubcapture.com.br": {"status": "ok|erro|manual", "detalhe": …, "em": iso}}
    provisionamento: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # visual + textos, validados por schemas/marcas.TemaMarca (nunca CSS livre)
    tema: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()


class MarcaAsset(Base):
    __tablename__ = "marca_assets"
    __table_args__ = (UniqueConstraint("marca_id", "tipo", name="uq_marca_assets_tipo"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    marca_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("marcas.id", ondelete="CASCADE"), index=True
    )
    tipo: Mapped[str] = mapped_column(String(24))
    content_type: Mapped[str] = mapped_column(String(80))
    nome_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    tamanho: Mapped[int] = mapped_column(Integer)
    # sha256 — versiona a URL pública (?v=…) para o cache longo do navegador
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()
