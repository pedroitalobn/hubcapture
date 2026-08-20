"""Obras — eixo de execução do ciclo (benchmark Virtù): SISMOB/SIMEC/CAIXA.

Fecha o ciclo captar → receber → executar → prestar contas. Cache global
compartilhado, RLS só-SELECT por município (igual a `propostas`/`repasses`/
`conformidades`). Guarda lat/long para o mapa no web.
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
from ._mixins import updated_at_col, uuid_pk

FONTES = ("sismob", "simec", "caixa")
SITUACOES = ("planejada", "em_execucao", "paralisada", "concluida", "cancelada")


class Obra(Base):
    __tablename__ = "obras"
    __table_args__ = (UniqueConstraint("fonte", "id_externo", name="uq_obras_fonte_id_externo"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(16), index=True)  # sismob|simec|caixa
    id_externo: Mapped[str] = mapped_column(String(128))
    municipio_ibge: Mapped[str] = mapped_column(String(7), index=True)
    municipio_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    nome: Mapped[str | None] = mapped_column(Text, nullable=True)
    objeto: Mapped[str | None] = mapped_column(Text, nullable=True)
    programa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eixo: Mapped[str | None] = mapped_column(String(32), nullable=True)  # saude|educacao|infra
    situacao: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    percentual_execucao: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    valor_investimento: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_repassado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    endereco: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = updated_at_col()
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
