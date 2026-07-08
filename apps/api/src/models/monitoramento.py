"""Monitoramento de proposta-chave (gera alertas na detecção de mudança)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class Monitoramento(Base):
    __tablename__ = "monitoramentos"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id", "proposta_id", name="uq_monitoramentos_usuario_proposta"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    proposta_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("propostas.id", ondelete="CASCADE")
    )
    ativo: Mapped[bool] = mapped_column(default=True)
    canais: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
