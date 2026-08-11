"""Schemas Pydantic da Proposta: canônica (interna) e de resposta (API)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PropostaCanonica(BaseModel):
    """Resultado da normalização/merge — o que o cache-first faz upsert."""

    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
    natureza_juridica: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    valor_total: Decimal | None = None
    contrapartida: Decimal | None = None
    situacao: str | None = None
    emenda: str | None = None
    prazos: list | None = None
    pendencias: list | None = None
    movimentacao: str | None = None
    data_atualizacao_fonte: date | None = None
    url_origem: str | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class PropostaRead(BaseModel):
    """Representação da proposta devolvida pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
    natureza_juridica: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    valor_total: Decimal | None = None
    contrapartida: Decimal | None = None
    situacao: str | None = None
    emenda: str | None = None
    prazos: list | None = None
    pendencias: list | None = None
    movimentacao: str | None = None
    data_atualizacao_fonte: date | None = None
    url_origem: str | None = None
    proveniencia: dict | None = None
    resumo_ia: str | None = None
    cache_atualizado_em: datetime | None = None


class OpcaoFiltro(BaseModel):
    """Uma opção de filtro com quantas propostas ela alcança."""

    valor: str
    label: str
    total: int


class FiltrosPropostas(BaseModel):
    """Opções disponíveis para os filtros de busca do painel.

    Calculadas sobre o que o usuário enxerga (RLS), para nunca oferecer um
    filtro que devolveria zero — e para o valor mín/máx sugerir o range real.
    """

    total: int
    municipios: list[OpcaoFiltro] = []
    naturezas_juridicas: list[OpcaoFiltro] = []
    fontes: list[OpcaoFiltro] = []
    situacoes: list[OpcaoFiltro] = []
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
