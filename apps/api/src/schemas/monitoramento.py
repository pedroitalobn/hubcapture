"""Schemas de monitoramento e alertas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..services import criterios_alerta


def _valida(escopo: str):
    """Valida a escolha contra o registro (§52) — chave inventada vira 422."""

    def _v(valor: list[str] | None) -> list[str] | None:
        try:
            return criterios_alerta.validar(valor, escopo)
        except ValueError as exc:  # mensagem do registro, com as chaves válidas
            raise ValueError(str(exc)) from exc

    return _v


class MonitoramentoCreate(BaseModel):
    proposta_id: uuid.UUID
    canais: list[str] = ["painel"]
    # None = padrões do registro; lista vazia = "não quero nenhum"
    criterios: list[str] | None = None

    _valida_criterios = field_validator("criterios")(_valida(criterios_alerta.ESCOPO_PROPOSTA))


class MonitoramentoBuscaCreate(BaseModel):
    """Monitorar FUTURAS propostas de um município (opcionalmente por área/fonte)."""

    municipio_ibge: str = Field(min_length=7, max_length=7)
    area: str | None = None
    fonte: str | None = None
    canais: list[str] = ["painel"]
    criterios: list[str] | None = None

    _valida_criterios = field_validator("criterios")(_valida(criterios_alerta.ESCOPO_TERRITORIO))


class MonitoramentoBuscaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    municipio_ibge: str
    area: str | None = None
    fonte: str | None = None
    ativo: bool
    canais: list[str] | None = None
    criterios: list[str] | None = None
    ultimo_alerta_em: datetime | None = None
    created_at: datetime


class MonitoramentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    proposta_id: uuid.UUID
    ativo: bool
    canais: list[str] | None = None
    criterios: list[str] | None = None
    ultimo_alerta_em: datetime | None = None
    created_at: datetime


class CriterioAlertaRead(BaseModel):
    """Item do catálogo que alimenta o multi-select de critérios."""

    chave: str
    rotulo: str
    descricao: str
    escopo: str
    padrao: bool


class AlertaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    proposta_id: uuid.UUID | None = None
    tipo: str | None = None
    payload: dict | None = None
    lido: bool
    created_at: datetime
