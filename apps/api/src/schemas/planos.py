"""Schemas de planos, convites e administração de usuários."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Planos ──────────────────────────────────────────────────────────────────
class PlanoLimites(BaseModel):
    """Config de gates do plano (§39). Chave AUSENTE = sem restrição.

    `modulos`/`fontes` são validados contra os registros (módulo/fonte que não
    existe é erro de digitação, não gate); `fontes` aceita grupo
    ("transferegov") ou connector id. Chaves extras são preservadas (legado e
    flags futuras vivem no mesmo jsonb).
    """

    model_config = ConfigDict(extra="allow")

    municipios_max: int | None = Field(default=None, ge=0)
    membros_max: int | None = Field(default=None, ge=0)
    modulos: list[str] | None = None
    fontes: list[str] | None = None
    features: dict[str, bool] | None = None

    @field_validator("modulos")
    @classmethod
    def _modulos_conhecidos(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from ..services import modulos as modulos_service

        desconhecidos = sorted(set(v) - {m["chave"] for m in modulos_service.MODULOS})
        if desconhecidos:
            raise ValueError(f"módulos desconhecidos: {', '.join(desconhecidos)}")
        return v

    @field_validator("fontes")
    @classmethod
    def _fontes_conhecidas(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from ..services import fontes as fontes_service

        conhecidas = set(fontes_service.GRUPOS) | set(fontes_service.HABILITADAS)
        desconhecidas = sorted(set(v) - conhecidas)
        if desconhecidas:
            raise ValueError(f"fontes desconhecidas: {', '.join(desconhecidas)}")
        return v

    def como_jsonb(self) -> dict:
        """Dict p/ persistir — sem os None (chave ausente = sem restrição)."""
        return self.model_dump(exclude_none=True)


class PlanoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=60)
    descricao: str | None = None
    preco_mensal: Decimal | None = None
    limites: PlanoLimites | None = None
    ativo: bool = True


class PlanoUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    preco_mensal: Decimal | None = None
    limites: PlanoLimites | None = None
    ativo: bool | None = None


class OpcaoCatalogo(BaseModel):
    """Um item escolhível na config do plano (módulo, fonte ou feature)."""

    chave: str
    label: str
    descricao: str | None = None


class PlanoOpcoes(BaseModel):
    """Catálogos p/ o editor de config do plano no painel admin (§39)."""

    modulos: list[OpcaoCatalogo] = []
    fontes: list[OpcaoCatalogo] = []  # grupos (vocabulário do onboarding)
    features: list[OpcaoCatalogo] = []


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


# ── Membros da conta (convites do próprio usuário, limitados pelo plano) ────
class MembroConviteCreate(BaseModel):
    """Convite de MEMBRO: o usuário chama alguém para a própria conta/equipe."""

    email: EmailStr
    papel: str | None = "equipe"
    expires_em_dias: int = Field(default=7, ge=1, le=90)


class MembroRead(BaseModel):
    """Um membro da conta — o convite e, se aceito, o usuário criado dele."""

    convite_id: uuid.UUID
    email: str
    papel: str | None = None
    status: str  # pendente | aceito | expirado
    expires_at: datetime | None = None
    created_at: datetime | None = None
    usuario_id: uuid.UUID | None = None  # preenchido quando o convite foi aceito
    nome: str | None = None


# ── Admin: criação/atribuição ───────────────────────────────────────────────
class AdminUsuarioCreate(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8)
    nome: str | None = None
    papel: str | None = None  # parlamentar | executivo | equipe
    plano_id: uuid.UUID | None = None
    is_superuser: bool = False  # permissão de admin da plataforma


class AdminUsuarioUpdate(BaseModel):
    """Ajuste de papel (role) e permissões de um usuário."""

    papel: str | None = None
    is_superuser: bool | None = None
    is_active: bool | None = None
    plano_id: uuid.UUID | None = None


class AdminUsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    nome: str | None = None
    papel: str | None = None
    plano_id: uuid.UUID | None = None
    is_superuser: bool
    is_active: bool
    is_verified: bool
    created_at: datetime | None = None


class AtribuirPlano(BaseModel):
    plano_id: uuid.UUID | None = None
