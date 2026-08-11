"""Schema canônico `Proposta` — resultado do merge multi-fonte.

Cache global compartilhado (dado público de governo): RLS filtra apenas o SELECT
por município de interesse; INSERT/UPDATE são livres para a role de app (senão o
upsert do cache-first quebraria numa policy WITH CHECK).
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

FONTES = (
    "transferegov_ff",
    "transferegov_esp",
    "transferegov_disc",
    "fns",
    "fnde",
    "serpro",
)

# Natureza jurídica do proponente/beneficiário, normalizada em slug (o rótulo
# bruto de cada fonte varia muito). Filtro de busca do painel; o de-para mora em
# `ingestion/normalizer.NATUREZA_JURIDICA_MAP`.
NATUREZAS_JURIDICAS: dict[str, str] = {
    "administracao_publica_municipal": "Administração pública municipal",
    "administracao_publica_estadual": "Administração pública estadual/distrital",
    "administracao_publica_federal": "Administração pública federal",
    "consorcio_publico": "Consórcio público",
    "organizacao_sociedade_civil": "Organização da sociedade civil",
    "empresa_publica": "Empresa pública / sociedade de economia mista",
    "outros": "Outros",
}


class Proposta(Base):
    __tablename__ = "propostas"
    __table_args__ = (
        UniqueConstraint("fonte", "id_externo", name="uq_propostas_fonte_id_externo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(255))
    numero_proposta: Mapped[str | None] = mapped_column(String(64), nullable=True)
    titulo: Mapped[str | None] = mapped_column(Text, nullable=True)
    objeto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao_superior: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modalidade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    natureza_juridica: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), index=True)
    municipio_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    contrapartida: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emenda: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prazos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    pendencias: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    movimentacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_atualizacao_fonte: Mapped[date | None] = mapped_column(Date, nullable=True)
    url_origem: Mapped[str | None] = mapped_column(Text, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resumo_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
