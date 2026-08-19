"""Configuração runtime da plataforma (credenciais de provider, URLs de fonte).

Nível-plataforma (sem RLS por-tenant). Gerenciada pelo painel admin via API.
Segredos são cifrados em repouso (Fernet) quando `cifrado=True`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import uuid_pk


class Configuracao(Base):
    __tablename__ = "configuracoes"

    id: Mapped[uuid.UUID] = uuid_pk()
    chave: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    valor: Mapped[str | None] = mapped_column(Text, nullable=True)
    secreto: Mapped[bool] = mapped_column(Boolean, default=False)
    cifrado: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria: Mapped[str | None] = mapped_column(String(40), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
