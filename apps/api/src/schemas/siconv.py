"""Schemas do pacote de dados abertos do SIconv (rotas de admin)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ArquivoSiconv(BaseModel):
    """Um arquivo do pacote, com o que se sabe dele SEM baixar."""

    tabela: str
    descricao: str
    #: tem destino no schema do Hub (entra na carga) ou é só conferência
    carrega: bool
    #: nome do ZIP que respondeu — None quando nenhum candidato serviu
    nome: str | None = None
    url: str | None = None
    disponivel: bool = False
    tamanho: int | None = None
    erro: str | None = None


class CargaSiconv(BaseModel):
    """Uma execução da carga (o que `sync_runs` guardou)."""

    status: str
    registros: int = 0
    iniciado_em: datetime | None = None
    finalizado_em: datetime | None = None
    erro: str | None = None


class CatalogoSiconv(BaseModel):
    base_url: str
    escopo_propostas: str
    #: municípios monitorados hoje — é o recorte da carga no escopo `territorio`
    municipios_monitorados: int
    tabelas_da_carga: list[str]
    arquivos: list[ArquivoSiconv]
    ultimas_cargas: list[CargaSiconv]


class PedidoCarga(BaseModel):
    """Disparo manual. Vazio = o mesmo recorte da carga agendada."""

    tabelas: list[str] = Field(default_factory=list)


class CargaIniciada(BaseModel):
    iniciada: bool
    tabelas: list[str]
    detalhe: str
