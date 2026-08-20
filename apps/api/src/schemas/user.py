"""Schemas Pydantic de usuário (fastapi-users) com os campos do domínio."""

from __future__ import annotations

import uuid

from fastapi_users import schemas
from pydantic import field_validator

from ._papel import papel_ou_none


class UserRead(schemas.BaseUser[uuid.UUID]):
    nome: str | None = None
    papel: str | None = None
    plano: str | None = None
    plano_id: uuid.UUID | None = None
    telefone_wpp: str | None = None
    optin_wpp: bool = False
    # conta de demonstração (sandbox de apresentação) — services/demo.py
    is_demo: bool = False


class UserCreate(schemas.BaseUserCreate):
    nome: str | None = None
    papel: str | None = None
    plano: str | None = None
    telefone_wpp: str | None = None
    optin_wpp: bool = False

    _papel = field_validator("papel", mode="before")(papel_ou_none)


class UserUpdate(schemas.BaseUserUpdate):
    nome: str | None = None
    papel: str | None = None
    plano: str | None = None
    telefone_wpp: str | None = None
    optin_wpp: bool | None = None

    _papel = field_validator("papel", mode="before")(papel_ou_none)
