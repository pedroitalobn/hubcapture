"""Schemas dos módulos da plataforma (liga/desliga eixos pelo painel admin)."""

from __future__ import annotations

from pydantic import BaseModel


class ModuloItem(BaseModel):
    chave: str  # 'captacao' | 'recebidos' | 'conformidade' | 'obras' | 'copiloto'
    label: str
    descricao: str | None = None
    padrao: bool
    ativo: bool


class ModuloSet(BaseModel):
    chave: str
    ativo: bool
