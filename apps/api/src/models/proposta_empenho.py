"""Empenho da proposta — o fato que diz se o recurso saiu do papel.

Entidade própria porque é 1-N: a proposta acumula empenhos (ordinários,
complementares, reforços) ao longo da execução, cada um com número, data e
valor. Vem de rota separada do módulo especiais, consultada pelo número da
proposta — não da linha do plano de ação.

Não confundir com `propostas.execucao.valor_empenhado` (§28): aquilo é o
AGREGADO que o painel da Visão Geral publica quando publica; aqui é o
documento, item a item, e é dele que sai o total quando o agregado não vem.

Cache global, RLS só-SELECT por município como `pareceres`/`proposta_emendas`.
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


class PropostaEmpenho(Base):
    __tablename__ = "proposta_empenhos"
    __table_args__ = (
        UniqueConstraint(
            "fonte", "id_externo", name="uq_proposta_empenhos_fonte_id_externo"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(128))

    # elos com a proposta — o empenho é consultado pelo NÚMERO DA PROPOSTA
    numero_proposta: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    numero_plano_acao: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)

    # o documento
    numero_empenho: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_empenho: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    tipo_empenho: Mapped[str | None] = mapped_column(String(64), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ano: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # dinheiro — o empenhado é o número que o gestor procura
    valor_empenhado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_anulado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_liquidado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # de onde saiu o recurso
    ug_emitente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gestao_emitente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    natureza_despesa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fonte_recurso: Mapped[str | None] = mapped_column(String(255), nullable=True)
    programa_trabalho: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
