"""Schemas do painel de configuração runtime (credenciais de provider)."""

from __future__ import annotations

from pydantic import BaseModel


class ConfigItem(BaseModel):
    chave: str
    label: str
    categoria: str
    secreto: bool
    configurado: bool
    origem: str  # 'banco' | 'padrao'
    valor: str | None = None  # segredos vêm mascarados


class ConfigSet(BaseModel):
    chave: str
    valor: str | None = None


class ConhecimentoCreate(BaseModel):
    titulo: str
    conteudo: str
    categoria: str | None = None
    tags: list[str] | None = None
