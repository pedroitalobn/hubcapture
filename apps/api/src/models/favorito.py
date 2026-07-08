"""Favoritos (usuario x proposta)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col


class Favorito(Base):
    __tablename__ = "favoritos"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    proposta_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("propostas.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = created_at_col()
