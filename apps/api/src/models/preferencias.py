"""Preferências capturadas no onboarding (fontes/áreas/monitorar)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class PreferenciasUsuario(Base):
    __tablename__ = "preferencias_usuario"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fontes: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    areas: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    monitorar_ativo: Mapped[bool] = mapped_column(default=True)
