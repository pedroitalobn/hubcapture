"""Convites para novos usuários. Nível-plataforma — sem RLS por-tenant.

Um admin (is_superuser) cria o convite (gera token); o convidado aceita definindo
a senha, o que cria o usuário com o papel/plano do convite.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk

STATUS = ("pendente", "aceito", "expirado")


class Convite(Base):
    __tablename__ = "convites"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    papel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plano_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("planos.id", ondelete="SET NULL"), nullable=True
    )
    convidado_por: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pendente")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
