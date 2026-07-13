"""Usuário (tenant = usuário individual). Base do fastapi-users + campos do domínio.

O atributo `hashed_password` do fastapi-users é mapeado para a coluna `senha_hash`
(convenção do schema canônico) — não cria coluna duplicada.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base

PAPEIS = ("parlamentar", "executivo", "equipe")


class Usuario(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "papel in ('parlamentar','executivo','equipe')", name="ck_usuarios_papel"
        ),
    )

    # renomeia a coluna herdada `hashed_password` -> `senha_hash`
    hashed_password: Mapped[str] = mapped_column("senha_hash", String(length=1024))

    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    papel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plano: Mapped[str | None] = mapped_column(String(50), nullable=True)  # legado (texto)
    plano_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("planos.id", ondelete="SET NULL"), nullable=True
    )
    telefone_wpp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    optin_wpp: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
