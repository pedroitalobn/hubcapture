"""Conexão do usuário com uma agenda externa (Google/Microsoft/Apple/CardDAV).

Uma linha por conta conectada. As credenciais (refresh token OAuth ou senha de
app do iCloud) ficam num blob **cifrado** (`core/crypto`) — nunca em claro, nunca
devolvidas pela API. `sync_token` guarda o cursor incremental do provedor
(syncToken do Google, deltaLink do Graph, CTag do CardDAV).

`contato_vinculos` é o de-para local↔remoto: sem ele, cada sync recriaria os
contatos do outro lado (e o delete nunca propagaria).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import updated_at_col, uuid_pk

PROVEDORES = ("google", "microsoft", "apple", "carddav")
STATUS = ("conectada", "expirada", "erro", "desconectada")
# importar = só puxa do provedor; exportar = só empurra; bidirecional = os dois
DIRECOES = ("bidirecional", "importar", "exportar")


class IntegracaoContatos(Base):
    __tablename__ = "integracoes_contatos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "provedor", "conta", name="uq_integracoes_contatos_conta"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    provedor: Mapped[str] = mapped_column(String(16))
    conta: Mapped[str] = mapped_column(String(255))  # e-mail/identificador remoto
    status: Mapped[str] = mapped_column(String(16), default="conectada")
    direcao: Mapped[str] = mapped_column(String(16), default="bidirecional")
    credenciais: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet
    sync_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultima_sync_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_contatos: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = updated_at_col()


class ContatoVinculo(Base):
    """De-para contato local ↔ contato remoto, com etag para detectar mudança."""

    __tablename__ = "contato_vinculos"
    __table_args__ = (
        UniqueConstraint("integracao_id", "id_externo", name="uq_contato_vinculos_externo"),
    )

    integracao_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("integracoes_contatos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    contato_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("contatos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id_externo: Mapped[str] = mapped_column(String(512))
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # hash do conteúdo canônico na última sincronização — base da detecção de
    # conflito (mudou dos dois lados?) e do "nada mudou, não escreve".
    hash_sincronizado: Mapped[str | None] = mapped_column(String(64), nullable=True)
    removido_remoto: Mapped[bool] = mapped_column(Boolean, default=False)
    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=True,
    )
