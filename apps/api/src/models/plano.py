"""Planos da plataforma (catálogo). Nível-plataforma — sem RLS por-tenant.

`limites` (jsonb) guarda as regras do plano: {municipios_max, fontes, alertas_wpp,
export_pdf, ...}. Atribuído ao usuário via `usuarios.plano_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class Plano(Base):
    __tablename__ = "planos"

    id: Mapped[uuid.UUID] = uuid_pk()
    nome: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    preco_mensal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    limites: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()
