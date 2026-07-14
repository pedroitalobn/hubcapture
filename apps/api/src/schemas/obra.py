"""Schemas de obras (execução — SISMOB/SIMEC/CAIXA)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ObraCanonica(BaseModel):
    fonte: str
    id_externo: str
    municipio_ibge: str
    municipio_nome: str | None = None
    uf: str | None = None
    nome: str | None = None
    objeto: str | None = None
    programa: str | None = None
    eixo: str | None = None
    situacao: str | None = None
    percentual_execucao: Decimal | None = None
    valor_investimento: Decimal | None = None
    valor_repassado: Decimal | None = None
    data_inicio: date | None = None
    data_fim_prevista: date | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    endereco: str | None = None
    orgao: str | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class ObraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    municipio_ibge: str
    municipio_nome: str | None = None
    uf: str | None = None
    nome: str | None = None
    objeto: str | None = None
    programa: str | None = None
    eixo: str | None = None
    situacao: str | None = None
    percentual_execucao: Decimal | None = None
    valor_investimento: Decimal | None = None
    valor_repassado: Decimal | None = None
    data_inicio: date | None = None
    data_fim_prevista: date | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    endereco: str | None = None
    orgao: str | None = None
    cache_atualizado_em: datetime | None = None


class SituacaoResumo(BaseModel):
    situacao: str
    total: int
    valor_investimento: Decimal


class ObrasResumo(BaseModel):
    """KPIs de execução + quebra por situação + obras (com geo p/ o mapa)."""

    total: int
    em_execucao: int
    concluidas: int
    paralisadas: int
    valor_investimento_total: Decimal
    valor_repassado_total: Decimal
    por_situacao: list[SituacaoResumo]
    obras: list[ObraRead]
