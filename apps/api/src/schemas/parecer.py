"""Schemas de parecer (tramitação do plano de trabalho)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ParecerCanonico(BaseModel):
    """Resultado da normalização — o que vai para o cache."""

    fonte: str
    id_externo: str
    numero_plano_trabalho: str
    numero_proposta: str | None = None
    municipio_ibge: str | None = None
    data_parecer: date | None = None
    esfera: str | None = None
    responsavel: str | None = None
    papel: str | None = None
    cargo: str | None = None
    situacao: str | None = None
    texto: str | None = None
    url_parecer: str | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class ParecerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_plano_trabalho: str
    numero_proposta: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    data_parecer: date | None = None
    esfera: str | None = None
    responsavel: str | None = None
    papel: str | None = None
    cargo: str | None = None
    situacao: str | None = None
    texto: str | None = None
    url_parecer: str | None = None
    cache_atualizado_em: datetime | None = None


class ParecerColeta(BaseModel):
    """Estado honesto da coleta — o gestor precisa distinguir 'não tem parecer'
    de 'não consegui consultar a fonte'."""

    numero_plano_trabalho: str | None = None
    status: str  # ok | sem_plano_trabalho | erro
    total: int = 0
    erro: str | None = None


class ParecerPagina(BaseModel):
    itens: list[ParecerRead] = []
    coleta: ParecerColeta
