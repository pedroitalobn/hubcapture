"""Schemas da assessoria orçamentária (contatos de WhatsApp)."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


class ContatoAssessoria(BaseModel):
    nome: str
    telefone: str
    descricao: str | None = None

    @field_validator("nome")
    @classmethod
    def _nome_obrigatorio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nome é obrigatório")
        return v

    @field_validator("telefone")
    @classmethod
    def _telefone_minimo(cls, v: str) -> str:
        v = v.strip()
        if len(re.sub(r"\D", "", v)) < 10:
            raise ValueError("telefone precisa de DDD + número (mínimo 10 dígitos)")
        return v


class ContatoAssessoriaRead(ContatoAssessoria):
    whatsapp_url: str


class AssessoriaContatosSet(BaseModel):
    contatos: list[ContatoAssessoria]
