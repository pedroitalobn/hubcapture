"""Schemas da central de demandas da Assessoria."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class EventoDemanda(BaseModel):
    """Uma linha do histórico — quem falou, quando e o que mudou."""

    em: str | None = None
    autor: str | None = None
    texto: str | None = None
    situacao: str | None = None


class DemandaCreate(BaseModel):
    assunto: str
    descricao: str | None = None
    municipio_ibge: str | None = None
    proposta_id: uuid.UUID | None = None

    @field_validator("assunto")
    @classmethod
    def _assunto_obrigatorio(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("assunto é obrigatório")
        return v


class DemandaComentario(BaseModel):
    """Mensagem nova na demanda; `situacao` só quando ela muda de estado."""

    texto: str = ""
    situacao: str | None = None


class DemandaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assunto: str
    descricao: str | None = None
    municipio_ibge: str | None = None
    proposta_id: uuid.UUID | None = None
    situacao: str
    origem: str
    historico: list[EventoDemanda] | None = None
    resolvida_em: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class DemandaFilaRead(DemandaRead):
    """A mesma demanda, na fila do admin — com quem pediu."""

    usuario_email: str | None = None
    usuario_nome: str | None = None
