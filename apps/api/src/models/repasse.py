"""Schema canônico `Repasse` — recursos RECEBIDOS pelo município (eixo complementar
às propostas de captação). Alimentado por N connectors (FNS, FNDE, FPM, Emendas…).

Cache global compartilhado (dado público), igual a `propostas`: RLS filtra apenas
o SELECT por município de interesse; INSERT/UPDATE livres para a role de app.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import uuid_pk

# fontes que alimentam repasses (recebidos)
FONTES_REPASSE = ("fns", "fnde", "fpm", "emendas", "transferegov_ff", "caixa")
# natureza do lançamento — permite a decomposição crédito/dedução do FPM
NATUREZAS = ("credito", "deducao", "repasse")


class Repasse(Base):
    __tablename__ = "repasses"
    __table_args__ = (UniqueConstraint("fonte", "id_externo", name="uq_repasses_fonte_id_externo"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(255))
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), index=True)
    municipio_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    data_repasse: Mapped[date | None] = mapped_column(Date, index=True)
    competencia: Mapped[str | None] = mapped_column(String(32), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orgao_superior: Mapped[str | None] = mapped_column(String(255), nullable=True)
    natureza: Mapped[str] = mapped_column(String(16), default="repasse")
    valor: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    documento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emenda: Mapped[bool] = mapped_column(Boolean, default=False)
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
