"""Conformidade fiscal (CAUC/CAPAG) — eixo fiscal do ciclo (benchmark Virtù).

Cache global compartilhado, RLS só-SELECT por município (igual a `propostas`/
`repasses`). Cobre os requisitos do CAUC (por seção) e o rating CAPAG.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import uuid_pk

TIPOS = ("cauc", "capag")
STATUS = ("comprovado", "a_comprovar", "desativado", "rating")


class Conformidade(Base):
    __tablename__ = "conformidades"
    __table_args__ = (
        UniqueConstraint(
            "municipio_ibge", "tipo", "numero", name="uq_conformidades_muni_tipo_numero"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    municipio_ibge: Mapped[str] = mapped_column(String(7), index=True)
    municipio_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tipo: Mapped[str] = mapped_column(String(8), index=True)  # cauc | capag
    numero: Mapped[str] = mapped_column(String(16))  # '1.1', '3.2.1', 'nota'
    secao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    orgao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
