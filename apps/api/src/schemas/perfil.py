"""Schemas do perfil do usuário — a lente que organiza toda a navegação.

O Hub Capture NÃO é orientado a fonte de dados (abas TransfereGov/FNS/…): a
navegação parte do PERFIL — o(s) município(s) que o usuário acompanha, suas
áreas de interesse e seu papel. Estes schemas descrevem esse perfil e a visão
geral agregada (as 4 dimensões do ciclo captar→receber→executar→prestar contas)
já filtrada pelo território do usuário via RLS.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MunicipioBusca(BaseModel):
    """Resultado da busca IBGE (nome → código) usada no onboarding conversacional."""

    ibge: str
    nome: str
    uf: str | None = None


class MunicipioPerfil(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ibge: str
    nome: str | None = None
    uf: str | None = None
    modo: str  # 'monitorado' | 'avulso'


class PlanoPerfil(BaseModel):
    """O plano do usuário visto pela navegação: nome + o que a assinatura libera."""

    nome: str | None = None
    slug: str | None = None
    municipios_max: int | None = None  # None = ilimitado
    membros_max: int | None = None  # convidados p/ conta; None = ilimitado
    features: dict[str, bool] = {}  # estado efetivo das features conhecidas
    fontes: list[str] | None = None  # grupos de fonte liberados; None = todos
    modulos: list[str] | None = None  # módulos incluídos no plano; None = todos


class OrigemFonte(BaseModel):
    """Uma origem de recurso que o usuário pode filtrar no painel.

    A escolha é sempre o GRUPO (§30) — "TransfereGov", "FNS" —, nunca o
    connector: o gestor não precisa saber que TransfereGov são cinco rotas de
    ingestão. `connectors` viaja só para o front poder rotular a origem de um
    registro sem consultar a API de novo.
    """

    chave: str
    label: str
    connectors: list[str] = []


class PerfilRead(BaseModel):
    """Identidade do usuário do ponto de vista da navegação."""

    nome: str | None = None
    papel: str | None = None  # parlamentar | executivo | equipe
    municipios: list[MunicipioPerfil] = []
    areas: list[str] = []
    fontes: list[str] = []
    # catálogo do filtro "origem do recurso" do trilho — só as origens que ESTE
    # perfil tem. Antes o front trazia uma lista fixa (com fontes fora do
    # recorte da v1 e o TransfereGov reduzido a UM dos seus connectors), então
    # marcar uma origem filtrava por um id que quase nenhum registro tinha.
    origens: list[OrigemFonte] = []
    monitorar_ativo: bool = True
    # módulos EFETIVOS: ativos na plataforma (§29) ∩ incluídos no plano (§39)
    modulos: list[str] = []
    plano: PlanoPerfil | None = None  # None = sem plano atribuído (sem restrição)
    # conta de DEMONSTRAÇÃO: o painel mostra a faixa de sandbox e esconde as
    # ações bloqueadas (zerar perfil, refazer onboarding, trocar senha)
    demo: bool = False


class ResetPerfilResultado(BaseModel):
    """O que a zeragem do perfil apagou — e o que ela só marcou/invalidou.

    Nada de cache global sai do banco (ver `services/perfil.zerar`):
    `propostas` conta as propostas do território marcadas como excluídas (soft
    delete — somem do painel e a coleta seguinte as ressuscita) e
    `cache_invalidado`, as linhas de repasses/conformidades/obras que voltaram
    a ser "velhas" e serão recoletadas.
    """

    municipios: int = 0
    propostas: int = 0
    favoritos: int = 0
    pastas: int = 0
    monitoramentos: int = 0
    alertas: int = 0
    cache_invalidado: int = 0


class RemocaoMunicipioResultado(BaseModel):
    """O que saiu ao remover UM município do território.

    Só conta o que é do tenant: o cache global (propostas, repasses, obras) não
    é tocado — a mesma cidade pode estar no território de outro cliente.
    """

    ibge: str
    buscas_monitoradas: int = 0


class QuebraDimensao(BaseModel):
    """Recorte rápido dentro de uma dimensão (ex.: propostas por natureza).

    É uma lente sobre o próprio território — não uma aba por fonte de dados.
    """

    chave: str  # ex.: 'entes_municipais' | 'outros'
    rotulo: str  # ex.: 'Entes municipais'
    total: int = 0
    href: str  # rota web já filtrada


class DimensaoResumo(BaseModel):
    """Um eixo do ciclo (captação/recebidos/conformidade/obras) para o perfil."""

    chave: str  # 'captacao' | 'recebidos' | 'conformidade' | 'obras'
    titulo: str
    total: int = 0  # nº de itens visíveis no território do usuário
    destaque: str | None = None  # métrica-resumo (ex. valor total, pendências)
    # rota web da dimensão; None = módulo de exploração desligado — o card
    # informa o número do território sem navegar (§40)
    href: str | None = None
    # recortes dentro da dimensão (vazio quando não há navegação)
    quebras: list[QuebraDimensao] = []
    # a dimensão responde ao filtro de ano do painel? Captação (safra da
    # proposta) e recebidos (ano do pagamento) respondem; conformidade e obras
    # são estado ATUAL do município — o card diz isso em vez de fingir recorte.
    recorte_ano: bool = True


class VisaoGeralPerfil(BaseModel):
    """'Meu painel': tudo o que importa no território do usuário, por dimensão."""

    papel: str | None = None
    municipios: list[MunicipioPerfil] = []
    areas: list[str] = []
    dimensoes: list[DimensaoResumo] = []


class NovidadeItem(BaseModel):
    """Uma novidade do território — proposta/verba recém-atualizada no cache."""

    tipo: str  # 'captacao' | 'recebido'
    titulo: str
    descricao: str | None = None
    valor: Decimal | None = None
    data: date | None = None
    # Safra do item — o MESMO critério do resto do app (`propostas.ano_de` na
    # captação, ano do repasse nos recebidos). É por ele que o painel filtra e
    # ordena: a data de COLETA classificaria uma proposta de 2019 como novidade
    # do ano corrente.
    ano: str | None = None
    fonte: str
    # nome da fonte como o gestor a chama ("TransfereGov — Discricionárias"):
    # o slug do connector na tela é plumbing de integração (§35)
    fonte_rotulo: str | None = None
    municipio_ibge: str | None = None
    municipio_nome: str | None = None
    uf: str | None = None
    href: str
    # id da proposta (só p/ tipo 'captacao') — permite favoritar direto do painel
    proposta_id: str | None = None
    # NR_PROPOSTA: a referência que o gestor procura no feed (§35). Não
    # confundir com `proposta_id` (UUID interno, que nunca aparece na tela).
    numero_proposta: str | None = None


class SyncRunStatus(BaseModel):
    """Última execução de coleta por fonte — o painel mostra o estado honesto."""

    model_config = ConfigDict(from_attributes=True)
    fonte: str | None = None
    status: str | None = None  # 'ok' | 'degradado' | 'erro'
    registros: int | None = None
    finalizado_em: datetime | None = None


class AnoDisponivel(BaseModel):
    """Uma safra com novidade no território — alimenta o filtro de ano do painel.

    Vem SEMPRE do território inteiro (ignora o ano já escolhido): senão, ao
    filtrar 2024 o próprio filtro perderia as outras opções e o usuário ficaria
    preso na safra que escolheu.
    """

    ano: str
    total: int = 0


class NovidadesPerfil(BaseModel):
    """Feed 'últimas novidades' do Meu painel, recortado pelo perfil (RLS)."""

    itens: list[NovidadeItem] = []
    sync_runs: list[SyncRunStatus] = []
    # anos com novidade, do mais recente para o mais antigo
    anos: list[AnoDisponivel] = []
