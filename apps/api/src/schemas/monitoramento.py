"""Schemas de monitoramento e alertas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MonitoramentoCreate(BaseModel):
    proposta_id: uuid.UUID
    canais: list[str] = ["painel"]


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
    proposta_id: uuid.UUID
    tipo: str | None = None
    payload: dict | None = None
    lido: bool
    created_at: datetime
