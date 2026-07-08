"""Schemas de planos, convites e administração de usuários."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Planos ──────────────────────────────────────────────────────────────────
class PlanoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=60)
    descricao: str | None = None
    preco_mensal: Decimal | None = None
    limites: dict | None = None
    ativo: bool = True


class PlanoUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    preco_mensal: Decimal | None = None
    limites: dict | None = None
    ativo: bool | None = None


class PlanoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str
    slug: str
    descricao: str | None = None
    preco_mensal: Decimal | None = None
    limites: dict | None = None
    ativo: bool


# ── Convites ────────────────────────────────────────────────────────────────
class ConviteCreate(BaseModel):
    email: EmailStr
    papel: str | None = None
    plano_id: uuid.UUID | None = None
    expires_em_dias: int = 7


class ConviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    token: str
    papel: str | None = None
    plano_id: uuid.UUID | None = None
    status: str
    expires_at: datetime | None = None
    created_at: datetime


class AceitarConvite(BaseModel):
    token: str
    senha: str = Field(min_length=8)
    nome: str | None = None


# ── Admin: criação/atribuição ───────────────────────────────────────────────
class AdminUsuarioCreate(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8)
    nome: str | None = None
    papel: str | None = None
    plano_id: uuid.UUID | None = None


class AtribuirPlano(BaseModel):
    plano_id: uuid.UUID | None = None
