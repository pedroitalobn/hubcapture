"""Schemas do empenho da proposta."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class EmpenhoCanonico(BaseModel):
    """Resultado da normalização — o que vai para o cache."""

    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    numero_plano_acao: str | None = None
    municipio_ibge: str | None = None
    numero_empenho: str | None = None
    data_empenho: date | None = None
    tipo_empenho: str | None = None
    situacao: str | None = None
    ano: str | None = None
    valor_empenhado: Decimal | None = None
    valor_anulado: Decimal | None = None
    valor_liquidado: Decimal | None = None
    valor_pago: Decimal | None = None
    ug_emitente: str | None = None
    gestao_emitente: str | None = None
    natureza_despesa: str | None = None
    fonte_recurso: str | None = None
    programa_trabalho: str | None = None
    observacao: str | None = None
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class EmpenhoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    numero_plano_acao: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    numero_empenho: str | None = None
    data_empenho: date | None = None
    tipo_empenho: str | None = None
    situacao: str | None = None
    ano: str | None = None
    valor_empenhado: Decimal | None = None
    valor_anulado: Decimal | None = None
    valor_liquidado: Decimal | None = None
    valor_pago: Decimal | None = None
    ug_emitente: str | None = None
    gestao_emitente: str | None = None
    natureza_despesa: str | None = None
    fonte_recurso: str | None = None
    programa_trabalho: str | None = None
    observacao: str | None = None
    cache_atualizado_em: datetime | None = None


class EmpenhoResumo(BaseModel):
    """Os totais — é o que a faixa de destaque da proposta mostra.

    `valor_empenhado` já vem LÍQUIDO das anulações: um empenho anulado que
    continuasse somando diria ao gestor que há recurso onde não há.
    """

    total: int = 0
    valor_empenhado: Decimal = Decimal("0")
    valor_anulado: Decimal = Decimal("0")
    valor_liquidado: Decimal = Decimal("0")
    valor_pago: Decimal = Decimal("0")
    # empenhado − pago: o "disponibilizado e ainda não utilizado" (§28)
    valor_a_utilizar: Decimal = Decimal("0")
    primeiro_empenho: date | None = None
    ultimo_empenho: date | None = None


class EmpenhoColeta(BaseModel):
    """Estado honesto da coleta — "sem empenho" ≠ "não consegui consultar"."""

    status: str  # ok | sem_chave | erro
    total: int = 0
    origem: str | None = None  # fonte | cache
    erro: str | None = None


class EmpenhoPagina(BaseModel):
    itens: list[EmpenhoRead] = []
    resumo: EmpenhoResumo = EmpenhoResumo()
    coleta: EmpenhoColeta
