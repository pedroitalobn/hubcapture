"""Schemas Pydantic da Proposta: canônica (interna) e de resposta (API)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator


class PropostaCanonica(BaseModel):
    """Resultado da normalização/merge — o que o cache-first faz upsert."""

    fonte: str
    id_externo: str
    numero_proposta: str | None = None
    numero_plano_trabalho: str | None = None

    # Fontes (FF/Especiais) às vezes devolvem identificadores como número puro
    # (ex.: numero_plano_trabalho=28431). O Pydantic 2 não coage int→str, então
    # normalizamos aqui em vez de deixar a coleta inteira quebrar por 1 campo.
    @field_validator(
        "id_externo",
        "numero_proposta",
        "numero_plano_trabalho",
        "emenda",
        mode="before",
    )
    @classmethod
    def _identificador_como_texto(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return str(int(v) if float(v).is_integer() else v)
        return v
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


class PublicacaoRead(BaseModel):
    """"Saiu ou não saiu?" — a resposta em três estados, nunca em dois.

    `sem_informacao` é resposta: a fonte não disse. Espremer isso em "não
    publicado" (ou, pior, em "publicado") é o que fazia a tela afirmar o que
    o portal desmentia.
    """

    estado: str  # publicado | nao_publicado | sem_informacao
    rotulo: str
    valor: str | None = None
    data: date | None = None
    #: de onde veio o dado exibido (consulta ao vivo, pacote, relatório)
    origem: str | None = None


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
    def publicacao(self) -> PublicacaoRead:
        """Estado da publicação do instrumento, já resolvido (ponto 09).

        A regra de leitura é uma só e mora na API (`services/publicacao`): o
        front que decidisse por conta própria acabaria discordando do alerta e
        do PDF, que é como "Publicado" apareceu numa proposta que a fonte dava
        como não publicada.
        """
        from ..services import publicacao as publicacao_service

        ex = self.execucao or {}
        estado = publicacao_service.do_execucao(ex)
        return PublicacaoRead(
            estado=estado,
            rotulo=publicacao_service.ROTULOS[estado],
            valor=ex.get("valor_publicado"),
            data=publicacao_service.data_publicacao(ex),
            # sem estado não há dado exibido, logo não há origem a atribuir
            origem=(
                publicacao_service.origem(ex)
                if estado != publicacao_service.SEM_INFORMACAO
                else None
            ),
        )

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
    # Quando a coleta mais recente DESTE recorte tocou o cache. A lista é lida
    # do banco (o sweep diário é quem alimenta), então sem este carimbo o painel
    # não tem como dizer de quando é o dado — e "o número mudou" vira mistério
    # em vez de "a coleta das 03h trouxe novidade".
    atualizado_em: datetime | None = None


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


class ResumoMes(BaseModel):
    """Barra do gráfico aprovado × desembolsado mês a mês (recorte de UMA safra)."""

    mes: str  # "01"…"12"
    rotulo: str  # "Janeiro"…
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
    # vazia quando o recorte não é de uma safra única — ver `propostas.resumo`
    por_mes: list[ResumoMes] = []
    pipeline: list[PipelineItem]
    convenios_vigentes: list[ConvenioVigente]
