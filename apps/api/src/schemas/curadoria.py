"""Schemas de onboarding, favoritos e pastas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._papel import papel_ou_none


# ── Onboarding ──────────────────────────────────────────────────────────────
class MunicipioIn(BaseModel):
    ibge: str = Field(min_length=7, max_length=7)
    nome: str | None = None
    uf: str | None = None


class OnboardingRequest(BaseModel):
    municipios: list[MunicipioIn]
    fontes: list[str] = []
    areas: list[str] = []
    monitorar_ativo: bool = True
    papel: str | None = None
    disparar_sync: bool = False
    # passo "ativar avisos" da jornada: conectar WhatsApp e escolher canais
    telefone_wpp: str | None = None
    optin_wpp: bool | None = None
    canais_alerta: list[str] = ["painel"]

    _papel = field_validator("papel", mode="before")(papel_ou_none)


class OnboardingResponse(BaseModel):
    municipios: int
    sync_disparado: bool


# ── Favoritos ───────────────────────────────────────────────────────────────
class FavoritoCreate(BaseModel):
    proposta_id: uuid.UUID


class FavoritoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    proposta_id: uuid.UUID
    created_at: datetime


# ── Pastas ──────────────────────────────────────────────────────────────────
class PastaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    cor: str | None = None


class PastaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    cor: str | None = None


class PastaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str
    cor: str | None = None
    created_at: datetime


class PastaPropostaCreate(BaseModel):
    proposta_id: uuid.UUID
