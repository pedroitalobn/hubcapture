"""Base de conhecimento do Copiloto (docs/tutoriais TransfereGov, FAQs).

Nível-plataforma (sem RLS) — conhecimento compartilhado, gerido pelo admin.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ._mixins import created_at_col, uuid_pk


class BaseConhecimento(Base):
    __tablename__ = "base_conhecimento"

    id: Mapped[uuid.UUID] = uuid_pk()
    titulo: Mapped[str] = mapped_column(String(255))
    conteudo: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
