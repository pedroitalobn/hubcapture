"""Schemas do documento digitalizado da proposta."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DocumentoCanonico(BaseModel):
    """Resultado da normalização — o que vai para o cache."""

    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    id_proposta_fonte: str | None = None
    municipio_ibge: str | None = None
    nome: str
    tipo: str | None = None
    data_upload: date | None = None
    url: str | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class DocumentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    nome: str
    tipo: str | None = None
    data_upload: date | None = None
    url: str | None = None
    cache_atualizado_em: datetime | None = None


class DocumentoColeta(BaseModel):
    """Estado da consulta — "não consegui" nunca pode virar "não tem".

    `sem_chave` é o caso em que a proposta não expõe o idProposta interno do
    SIconv: não dá nem para perguntar, e isso é diferente de perguntar e a
    fonte responder vazio.
    """

    status: str = "ok"  # ok | erro | sem_chave | fonte_nao_suportada
    total: int = 0
    erro: str | None = None


class DocumentoPagina(BaseModel):
    """Resposta do endpoint: os documentos e o estado da consulta."""

    itens: list[DocumentoRead] = []
    coleta: DocumentoColeta = DocumentoColeta()
