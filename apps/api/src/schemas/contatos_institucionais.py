"""Schemas do diretório institucional (gabinetes, assessorias, SEIs)."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class ContatoInstitucional(BaseModel):
    """Uma entrada do diretório. `nome` OU `orgao` basta — parte das linhas é
    o próprio gabinete ("Gabinete do Ministro da Saúde"), sem pessoa nomeada."""

    nome: str = ""
    orgao: str | None = None
    cargo: str | None = None
    categoria: str = "outros"
    email: str | None = None
    telefone: str | None = None
    # número do processo no SEI + link, quando o órgão publica
    sei: str | None = None
    sei_url: str | None = None
    observacao: str | None = None

    @field_validator("nome")
    @classmethod
    def _limpa(cls, v: str) -> str:
        return (v or "").strip()


class ContatoInstitucionalRead(ContatoInstitucional):
    categoria_rotulo: str
    whatsapp_url: str | None = None


class CategoriaInstitucional(BaseModel):
    """Opção de filtro da tela (o eixo pelo qual o gestor procura)."""

    chave: str
    rotulo: str


class DiretorioInstitucionalSet(BaseModel):
    contatos: list[ContatoInstitucional]
