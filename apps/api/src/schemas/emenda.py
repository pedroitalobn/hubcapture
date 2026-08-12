"""Schemas da emenda parlamentar que financia a proposta (e seu autor)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class EmendaCanonica(BaseModel):
    """Resultado da normalização — o que vai para o cache."""

    fonte: str
    id_externo: str
    numero_plano_acao: str | None = None
    numero_proposta: str | None = None
    municipio_ibge: str | None = None
    codigo_emenda: str | None = None
    numero_emenda: str | None = None
    ano: int | None = None
    tipo_emenda: str | None = None
    parlamentar: str | None = None
    partido: str | None = None
    uf_parlamentar: str | None = None
    cargo_parlamentar: str | None = None
    codigo_parlamentar: str | None = None
    valor: Decimal | None = None
    valor_empenhado: Decimal | None = None
    valor_pago: Decimal | None = None
    funcao: str | None = None
    situacao: str | None = None
    url_origem: str | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class EmendaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_plano_acao: str | None = None
    numero_proposta: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    codigo_emenda: str | None = None
    numero_emenda: str | None = None
    ano: int | None = None
    tipo_emenda: str | None = None
    parlamentar: str | None = None
    partido: str | None = None
    uf_parlamentar: str | None = None
    cargo_parlamentar: str | None = None
    valor: Decimal | None = None
    valor_empenhado: Decimal | None = None
    valor_pago: Decimal | None = None
    funcao: str | None = None
    situacao: str | None = None
    url_origem: str | None = None
    cache_atualizado_em: datetime | None = None


class EmendaColeta(BaseModel):
    """Estado honesto da coleta — "não tem emenda" ≠ "não consegui consultar".

    `origem` distingue de onde veio o que está na tela: `fonte` (rota do módulo
    consultada agora), `registro_fonte` (o que o próprio plano de ação já
    trazia) ou `cache`.
    """

    status: str  # ok | sem_chave | erro
    total: int = 0
    origem: str | None = None
    erro: str | None = None


class EmendaPagina(BaseModel):
    itens: list[EmendaRead] = []
    coleta: EmendaColeta
