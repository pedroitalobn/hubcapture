"""Parecer — a tramitação do PLANO DE TRABALHO vinculado à proposta.

Na fonte, o parecer não é emitido "sobre a proposta": é emitido sobre o plano de
trabalho dela, e a mesma proposta acumula vários ao longo da análise (concedente
e convenente, em datas diferentes). Por isso entidade própria, com
`numero_plano_trabalho` como chave de consulta — é o que o gestor tem em mãos.

Cache global, RLS só-SELECT por município (igual a `propostas`/`obras`). O
`municipio_ibge` é desnormalizado só para a policy recortar sem join.
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

# quem emitiu — a fonte fala em esfera, não em órgão
ESFERAS = ("concedente", "convenente")


class Parecer(Base):
    __tablename__ = "pareceres"
    __table_args__ = (
        UniqueConstraint("fonte", "id_externo", name="uq_pareceres_fonte_id_externo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32), index=True)
    id_externo: Mapped[str] = mapped_column(String(128))

    # elo com a proposta — o parecer é DO plano de trabalho
    numero_plano_trabalho: Mapped[str] = mapped_column(String(64), index=True)
    numero_proposta: Mapped[str | None] = mapped_column(String(64), nullable=True)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)

    data_parecer: Mapped[date | None] = mapped_column(Date, nullable=True)
    esfera: Mapped[str | None] = mapped_column(String(32), nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    papel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # veredito da análise (valores fechados do spec: Aprovar/Reprovar/
    # Solicitar Complementação/Não se aplica) — é o que o gestor quer ler
    situacao: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # estado da própria análise (Concluída | Em elaboração) — parecer em
    # elaboração ainda não é decisão
    situacao_analise: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # situação do planejamento do plano (APROVADO, REPROVADO, ...)
    situacao_planejamento: Mapped[str | None] = mapped_column(String(32), nullable=True)
    orgao_analise: Mapped[str | None] = mapped_column(String(255), nullable=True)
    codigo_siorg_orgao: Mapped[str | None] = mapped_column(String(32), nullable=True)
    valor_reprovado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_parecer: Mapped[str | None] = mapped_column(Text, nullable=True)

    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proveniencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = updated_at_col()
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
