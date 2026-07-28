"""Schemas de monitoramento e alertas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MonitoramentoCreate(BaseModel):
    proposta_id: uuid.UUID
    canais: list[str] = ["painel"]


class MonitoramentoBuscaCreate(BaseModel):
    """Monitorar FUTURAS propostas de um município (opcionalmente por área/fonte)."""

    municipio_ibge: str = Field(min_length=7, max_length=7)
    area: str | None = None
    fonte: str | None = None
    canais: list[str] = ["painel"]


class MonitoramentoBuscaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    municipio_ibge: str
    area: str | None = None
    fonte: str | None = None
    ativo: bool
    canais: list[str] | None = None
    ultimo_alerta_em: datetime | None = None
    created_at: datetime


class MonitoramentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    proposta_id: uuid.UUID
    ativo: bool
    canais: list[str] | None = None
    created_at: datetime


class AlertaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    proposta_id: uuid.UUID | None = None
    tipo: str | None = None
    payload: dict | None = None
    lido: bool
    created_at: datetime
