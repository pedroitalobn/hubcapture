"""Schemas das Oportunidades — programas abertos para o território (§63)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class JanelaRead(BaseModel):
    tipo: str  # voluntaria | emenda | beneficiario
    rotulo: str
    como: str
    inicio: date | None = None
    fim: date | None = None  # None = "apto" na consulta oficial, sem data (§64)
    status: str  # aberta | em_breve
    dias_restantes: int | None = None


class MunicipioElegivel(BaseModel):
    ibge: str
    nome: str | None = None
    uf: str | None = None
    historico: bool = False
    conhece_orgao: bool = False


class MotivoRead(BaseModel):
    chave: str
    texto: str


class CategoriaRead(BaseModel):
    slug: str
    rotulo: str


class ProgramaOportunidade(BaseModel):
    id: uuid.UUID
    codigo: str | None = None
    nome: str | None = None
    orgao_superior: str | None = None
    orgao: str | None = None
    situacao: str | None = None
    ano: int | None = None
    modalidades: list[str] = []
    naturezas: list[str] = []
    aceita_municipio: bool = True
    ufs: list[str] = []
    janelas: list[JanelaRead]
    prazo_final: date | None = None
    dias_restantes: int | None = None
    municipios: list[MunicipioElegivel]
    categorias: list[CategoriaRead] = []
    motivos: list[MotivoRead] = []
    recomendado: bool = False
    url_consulta: str


class FacetaOpcao(BaseModel):
    valor: str
    rotulo: str
    total: int


class CatalogoEstado(BaseModel):
    total: int
    atualizado_em: datetime | None = None


class MunicipioRecorte(BaseModel):
    ibge: str
    nome: str | None = None
    uf: str | None = None


class OportunidadesResposta(BaseModel):
    programas: list[ProgramaOportunidade]
    total: int
    recomendados: int
    encerrando: int
    municipios: list[MunicipioRecorte]
    catalogo: CatalogoEstado
    facetas: dict[str, list[FacetaOpcao]]
    hoje: date
