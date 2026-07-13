"""Schemas Pydantic de Repasse: canônico (interno), leitura (API) e visão geral."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RepasseCanonico(BaseModel):
    """Resultado da normalização — o que o cache-first faz upsert."""

    fonte: str
    id_externo: str
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    data_repasse: date | None = None
    competencia: str | None = None
    descricao: str | None = None
    categoria: str | None = None
    orgao_superior: str | None = None
    natureza: str = "repasse"
    valor: Decimal | None = None
    documento: str | None = None
    emenda: bool = False
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class RepasseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    data_repasse: date | None = None
    competencia: str | None = None
    descricao: str | None = None
    categoria: str | None = None
    orgao_superior: str | None = None
    natureza: str
    valor: Decimal | None = None
    documento: str | None = None
    emenda: bool
    detalhe: dict | None = None
    cache_atualizado_em: datetime | None = None


class FonteResumo(BaseModel):
    """Card por fonte no dashboard (ícone/valor/nº de movimentações)."""

    fonte: str
    total: Decimal
    movimentacoes: int


class RepassesPorDia(BaseModel):
    """Item do feed agrupado por data, com subtotal do dia."""

    data: date
    subtotal: Decimal
    itens: list[RepasseRead]


class VisaoGeral(BaseModel):
    """Painel consolidado: KPI + fontes + feed agrupado por data."""

    total_pago: Decimal
    movimentacoes: int
    inicio: date | None = None
    fim: date | None = None
    fontes: list[FonteResumo]
    feed: list[RepassesPorDia]
