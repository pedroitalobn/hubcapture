"""Alertas gerados pela detecção de mudança (status/prazo/pendência)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    # nullable: alertas de oportunidade ("recursos disponíveis sem proposta
    # cadastrada") não apontam para uma proposta existente
    proposta_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("propostas.id", ondelete="CASCADE"),
        nullable=True,
    )
    tipo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lido: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = created_at_col()
