"""Schemas do perfil do usuário — a lente que organiza toda a navegação.

O Hub Capture NÃO é orientado a fonte de dados (abas TransfereGov/FNS/…): a
navegação parte do PERFIL — o(s) município(s) que o usuário acompanha, suas
áreas de interesse e seu papel. Estes schemas descrevem esse perfil e a visão
geral agregada (as 4 dimensões do ciclo captar→receber→executar→prestar contas)
já filtrada pelo território do usuário via RLS.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MunicipioPerfil(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ibge: str
    nome: str | None = None
    uf: str | None = None
    modo: str  # 'monitorado' | 'avulso'


class PerfilRead(BaseModel):
    """Identidade do usuário do ponto de vista da navegação."""

    nome: str | None = None
    papel: str | None = None  # parlamentar | executivo | equipe
    municipios: list[MunicipioPerfil] = []
    areas: list[str] = []
    fontes: list[str] = []
    monitorar_ativo: bool = True
    modulos: list[str] = []  # módulos ativos na plataforma (lentes do menu)


class DimensaoResumo(BaseModel):
    """Um eixo do ciclo (captação/recebidos/conformidade/obras) para o perfil."""

    chave: str  # 'captacao' | 'recebidos' | 'conformidade' | 'obras'
    titulo: str
    total: int = 0  # nº de itens visíveis no território do usuário
    destaque: str | None = None  # métrica-resumo (ex. valor total, pendências)
    href: str  # rota web da dimensão


class VisaoGeralPerfil(BaseModel):
    """'Meu painel': tudo o que importa no território do usuário, por dimensão."""

    papel: str | None = None
    municipios: list[MunicipioPerfil] = []
    areas: list[str] = []
    dimensoes: list[DimensaoResumo] = []
