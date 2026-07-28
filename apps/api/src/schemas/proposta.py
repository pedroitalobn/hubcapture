"""Schemas Pydantic da Proposta: canônica (interna) e de resposta (API)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field


class PropostaCanonica(BaseModel):
    """Resultado da normalização/merge — o que o cache-first faz upsert."""

    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    descricao: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
    ano: int | None = None
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
    execucao: dict | None = None
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
    descricao: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
    ano: int | None = None
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
    execucao: dict | None = None
    resumo_ia: str | None = None
    cache_atualizado_em: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tipo(self) -> str:
        """Eixo da jornada: 'cadastrada' (já existe) ou 'disponivel' (oportunidade)."""
        from ..services.propostas import classificar_tipo

        return classificar_tipo(self.situacao)


class AnoResumo(BaseModel):
    """Um exercício disponível no território do usuário (alimenta os filtros)."""

    ano: int | None = None  # None = propostas sem exercício identificado
    total: int = 0
    valor_total: Decimal = Decimal(0)


class PropostasResumo(BaseModel):
    """KPIs da captação já recortados pelo ano em foco + os anos disponíveis."""

    ano: int | None = None  # exercício em foco (None = todos)
    total: int = 0
    valor_total: Decimal = Decimal(0)
    contrapartida_total: Decimal = Decimal(0)
    municipios: int = 0
    por_ano: list[AnoResumo] = []
    propostas: list[PropostaRead] = []


class PropostaPrazo(BaseModel):
    """Proposta com prazos vencendo na janela consultada (visão estruturada)."""

    proposta: PropostaRead
    prazos_na_janela: list[dict]
