"""Schemas Pydantic de Repasse: canônico (interno), leitura (API) e visão geral."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RepasseCanonico(BaseModel):
    """Resultado da normalização — o que o cache-first faz upsert."""

    fonte: str
    id_externo: str
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    data_repasse: date | None = None
    competencia: str | None = None
    descricao: str | None = None
    categoria: str | None = None
    orgao_superior: str | None = None
    natureza: str = "repasse"
    valor: Decimal | None = None
    documento: str | None = None
    emenda: bool = False
    detalhe: dict | None = None
    proveniencia: dict | None = None
    hash_conteudo: str | None = None


class RepasseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    data_repasse: date | None = None
    competencia: str | None = None
    descricao: str | None = None
    categoria: str | None = None
    orgao_superior: str | None = None
    natureza: str
    valor: Decimal | None = None
    documento: str | None = None
    emenda: bool
    detalhe: dict | None = None
    cache_atualizado_em: datetime | None = None


class FonteResumo(BaseModel):
    """Card por fonte no dashboard (ícone/valor/nº de movimentações)."""

    fonte: str
    total: Decimal
    movimentacoes: int


class RepassesPorDia(BaseModel):
    """Item do feed agrupado por data, com subtotal do dia.

    `data` é opcional porque nem toda fonte publica a data do pagamento: o FNS
    entrega o AGREGADO do exercício (quanto o município recebeu no ano, por
    tipo), sem OB nem dia. Quando falta, `competencia` diz de que exercício é o
    grupo — sem os dois o lançamento simplesmente sumia da tela, com o valor
    contado no card da fonte: o gestor via R$ 70 mi no total do FNS e um feed
    que não mencionava o FNS em lugar nenhum.
    """

    data: date | None = None
    competencia: str | None = None
    subtotal: Decimal
    itens: list[RepasseRead]


class VisaoGeral(BaseModel):
    """Painel consolidado: KPI + fontes + feed agrupado por data."""

    total_pago: Decimal
    movimentacoes: int
    inicio: date | None = None
    fim: date | None = None
    fontes: list[FonteResumo]
    feed: list[RepassesPorDia]


# ── Emendas parlamentares (gestão de emendas) ───────────────────────────────


class EmendaItem(BaseModel):
    """Uma emenda que beneficiou o município, achatada para a tela."""

    id: uuid.UUID
    codigo: str
    numero: str | None = None
    parlamentar: str | None = None
    partido: str | None = None
    modalidade: str | None = None  # individual | bancada | comissão…
    area: str | None = None  # função orçamentária
    orgao_superior: str | None = None
    ano: str | None = None
    empenhado: Decimal
    pago: Decimal
    percentual_executado: float
    data_repasse: date | None = None
    descricao: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None


class SerieAnoEmendas(BaseModel):
    """Ponto do gráfico de evolução anual (pago × empenhado)."""

    ano: str
    empenhado: Decimal
    pago: Decimal


class DistribuicaoItem(BaseModel):
    """Fatia de uma distribuição (por modalidade ou por área/função)."""

    chave: str
    valor: Decimal
    quantidade: int


class RankingParlamentar(BaseModel):
    """Linha do ranking de parlamentares que destinaram recursos ao município."""

    parlamentar: str
    partido: str | None = None
    empenhado: Decimal
    pago: Decimal
    emendas: int


class OpcoesEmendas(BaseModel):
    """Valores disponíveis para os filtros da tela (só o que existe)."""

    anos: list[str] = []
    modalidades: list[str] = []
    parlamentares: list[str] = []
    orgaos: list[str] = []


class ResumoEmendas(BaseModel):
    """Painel de emendas: cards, gráficos, ranking, lista e opções de filtro."""

    empenhado: Decimal
    pago: Decimal
    percentual_executado: float
    emendas: int
    por_ano: list[SerieAnoEmendas]
    por_modalidade: list[DistribuicaoItem]
    por_area: list[DistribuicaoItem]
    ranking_parlamentares: list[RankingParlamentar]
    itens: list[EmendaItem]
    opcoes: OpcoesEmendas
