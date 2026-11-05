"""Schemas da API de integração (§67): chaves, consumo e "quem sou eu"."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Escopo = Literal["leitura", "escrita"]


class ApiChaveCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120, description="Para que serve a chave")
    escopo: Escopo = Field(
        default="leitura", description="'leitura' só faz GET; 'escrita' também altera dados"
    )
    expira_em: datetime | None = None


class AdminApiChaveCreate(ApiChaveCreate):
    usuario_id: uuid.UUID
    # sobrepõem o plano/padrão do servidor para ESTA chave
    limite_por_minuto: int | None = Field(default=None, ge=1, le=10000)
    limite_por_dia: int | None = Field(default=None, ge=1, le=10_000_000)


class ApiChaveRead(BaseModel):
    id: uuid.UUID
    nome: str
    prefixo: str
    ambiente: str
    escopo: str
    ativa: bool
    limite_por_minuto: int
    limite_por_dia: int
    uso_hoje: int = 0
    bloqueadas_hoje: int = 0
    uso_30_dias: int = 0
    ultimo_uso_em: datetime | None = None
    expira_em: datetime | None = None
    revogada_em: datetime | None = None
    created_at: datetime
    # só na visão do admin
    usuario_id: uuid.UUID | None = None
    usuario_email: str | None = None


class ApiChaveCriada(ApiChaveRead):
    chave: str = Field(description="A chave completa. Aparece UMA vez — guarde agora.")


class ChavesDaConta(BaseModel):
    """O que a tela "Integração via API" de Minha conta precisa."""

    disponivel: bool
    motivo: str | None = None
    ambiente: str
    sandbox: bool
    maximo: int
    chaves: list[ApiChaveRead] = []


class ChaveAtual(BaseModel):
    prefixo: str
    nome: str
    escopo: str
    limite_por_minuto: int
    limite_por_dia: int


class DeveloperMe(BaseModel):
    ambiente: str
    sandbox: bool
    autenticacao: Literal["api_key", "jwt"]
    usuario_id: uuid.UUID
    email: str
    nome: str | None = None
    municipios: list[str] = []
    chave: ChaveAtual | None = None
    documentacao: str = "/api/v1/docs"


class SandboxReset(BaseModel):
    municipios: int
    mensagem: str
