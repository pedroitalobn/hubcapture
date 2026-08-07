"""Schemas de conformidade fiscal (CAUC/CAPAG)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ConformidadeCanonica(BaseModel):
    municipio_ibge: str
    municipio_nome: str | None = None
    uf: str | None = None
    tipo: str  # cauc | capag
    numero: str
    secao: str | None = None
    descricao: str | None = None
    status: str | None = None
    validade: date | None = None
    orgao: str | None = None
    valor: Decimal | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class ConformidadeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    municipio_ibge: str
    # o município (nomeado) identifica o requisito; `numero` é dado secundário
    municipio_nome: str | None = None
    uf: str | None = None
    tipo: str
    numero: str
    secao: str | None = None
    descricao: str | None = None
    status: str | None = None
    validade: date | None = None
    orgao: str | None = None
    valor: Decimal | None = None
    detalhe: dict | None = None
    cache_atualizado_em: datetime | None = None


class SecaoResumo(BaseModel):
    secao: str
    total: int
    comprovados: int
    a_comprovar: int
    desativados: int


class ConformidadeResumo(BaseModel):
    """CAUC: KPIs por status + por seção. CAPAG: rating separado."""

    total: int
    comprovados: int
    a_comprovar: int
    desativados: int
    secoes: list[SecaoResumo]
    capag: ConformidadeRead | None = None
    requisitos: list[ConformidadeRead]
