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
    numero_plano_trabalho: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
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
    data_proposta: date | None = None
    data_atualizacao_fonte: date | None = None
    url_origem: str | None = None
    proveniencia: dict | None = None
    execucao: dict | None = None
    dados_fonte: dict | None = None
    hash_conteudo: str | None = None


class CategoriaTag(BaseModel):
    """Pílula de categoria: o slug (filtrável) e o rótulo (exibível)."""

    slug: str
    rotulo: str


class PropostaRead(BaseModel):
    """Representação da proposta devolvida pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    numero_plano_trabalho: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
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
    data_proposta: date | None = None
    data_atualizacao_fonte: date | None = None
    url_origem: str | None = None
    proveniencia: dict | None = None
    execucao: dict | None = None
    dados_fonte: dict | None = None
    resumo_ia: str | None = None
    categorias_ia: list[str] | None = None
    cache_atualizado_em: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def categorias(self) -> list[CategoriaTag]:
        """Pílulas prontas para exibição (slug + rótulo) — o painel não traduz nada.

        Sem curadoria gravada, classifica na hora pelo texto: proposta recém
        coletada já chega ao painel com pílula.
        """
        from ..ai import categorias as categorias_ai

        slugs = self.categorias_ia or categorias_ai.classificar(
            self.titulo, self.objeto, self.orgao_superior, self.modalidade
        )
        return [CategoriaTag(**c) for c in categorias_ai.rotular(slugs)]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tipo(self) -> str:
        """Eixo da jornada: 'cadastrada' (já existe) ou 'disponivel' (oportunidade)."""
        from ..services.propostas import classificar_tipo

        return classificar_tipo(self.situacao)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def natureza_juridica(self) -> str | None:
        """Slug da natureza jurídica elegível ('municipal', 'consorcio'…)."""
        from ..services.propostas import classificar_natureza_juridica

        return classificar_natureza_juridica((self.execucao or {}).get("natureza_juridica"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ano(self) -> str | None:
        """Ano de CRIAÇÃO da proposta (ANO_PROP na fonte) — o que o cabeçalho
        mostra e o filtro de ano usa como safra."""
        from ..services.propostas import ano_de

        return ano_de(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def valor_global(self) -> Decimal | None:
        """Valor global da proposta (VL_GLOBAL_PROP na fonte) — o que o card
        "Empenho" do detalhe mostra."""
        from ..services.propostas import valor_global_de

        return valor_global_de(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def prazo_final(self) -> date | None:
        """Prazo mais próximo declarado (alimenta o contador do card)."""
        datas = []
        for prazo in self.prazos or []:
            try:
                datas.append(date.fromisoformat(str((prazo or {}).get("data_limite"))[:10]))
            except (TypeError, ValueError):
                continue
        return min(datas) if datas else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dias_restantes(self) -> int | None:
        """Dias até o prazo final (negativo = vencido); None sem prazo."""
        prazo = self.prazo_final
        return (prazo - date.today()).days if prazo else None


class PropostasPagina(BaseModel):
    """Uma página da listagem + o total do recorte (o 'carregar mais' do painel).

    `total` é do recorte inteiro, já com os filtros aplicados — é ele que diz se
    ainda há próxima página, não o tamanho de `itens`.
    """

    itens: list[PropostaRead]
    total: int
    limite: int | None = None
    offset: int = 0


class PropostaPrazo(BaseModel):
    """Proposta com prazos vencendo na janela consultada (visão estruturada)."""

    proposta: PropostaRead
    prazos_na_janela: list[dict]


# ── Filtros: opções dos dropdowns com contagem ──────────────────────────────


class FacetaOpcao(BaseModel):
    """Uma opção de filtro com o número de propostas no recorte atual."""

    valor: str
    rotulo: str
    total: int


class PropostasFacetas(BaseModel):
    """Opções por dimensão de filtro — o que existe no território consultado."""

    municipio: list[FacetaOpcao] = []
    uf: list[FacetaOpcao] = []
    fonte: list[FacetaOpcao] = []
    modalidade: list[FacetaOpcao] = []
    orgao: list[FacetaOpcao] = []
    situacao: list[FacetaOpcao] = []
    natureza_juridica: list[FacetaOpcao] = []
    qualificacao: list[FacetaOpcao] = []
    categoria: list[FacetaOpcao] = []
    ano: list[FacetaOpcao] = []
    mes: list[FacetaOpcao] = []
    tipo: list[FacetaOpcao] = []


# ── Resumo consolidado da captação ──────────────────────────────────────────


class ResumoCards(BaseModel):
    """Cartões financeiros do topo do resumo."""

    valor_conveniado: Decimal
    valor_desembolsado: Decimal
    valor_empenhado: Decimal
    valor_pago: Decimal
    valor_publicado: Decimal
    propostas_publicadas: int
    valor_a_utilizar: Decimal
    transferencias: int
    convenios_iniciados: int
    convenios_em_execucao: int
    oportunidades_abertas: int


class ResumoAno(BaseModel):
    """Barra do gráfico aprovado × desembolsado por ano."""

    ano: str
    aprovado: Decimal
    desembolsado: Decimal


class PipelineItem(BaseModel):
    """Etapa do pipeline de propostas (agrupado por situação da fonte)."""

    situacao: str
    quantidade: int
    valor: Decimal


class ConvenioVigente(BaseModel):
    """Convênio em execução com o percentual já desembolsado."""

    id: uuid.UUID
    titulo: str | None = None
    orgao_superior: str | None = None
    modalidade: str | None = None
    valor_global: Decimal
    desembolsado: Decimal
    percentual_desembolso: float
    fim_vigencia: date | None = None
    dias_restantes: int | None = None


class ResumoCaptacao(BaseModel):
    """Resumo consolidado: cards, série anual, pipeline e convênios vigentes."""

    cards: ResumoCards
    por_ano: list[ResumoAno]
    pipeline: list[PipelineItem]
    convenios_vigentes: list[ConvenioVigente]
