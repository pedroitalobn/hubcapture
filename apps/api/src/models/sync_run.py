"""Execução de sync (agendado e avulso). Operacional — sem RLS.

Registra incidentes de fonte; nunca engolir erro silenciosamente.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import uuid_pk


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint("tipo in ('agendado','avulso')", name="ck_sync_runs_tipo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # null para sync global (agendado sem dono)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    fonte: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tipo: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    registros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iniciado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
