"""Schemas de contatos e das integrações de agenda externa.

`ContatoCanonico` é a língua franca do módulo: tudo que entra de um provedor
(Google People, Microsoft Graph, CardDAV/iCloud, vCard) vira isso antes de tocar
o banco, e tudo que sai para um provedor parte disso. Adicionar provedor = novo
mapeamento para/de `ContatoCanonico`, sem mexer no motor de sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContatoEmail(BaseModel):
    tipo: str | None = None  # trabalho|pessoal|outro
    valor: str


class ContatoTelefone(BaseModel):
    tipo: str | None = None  # celular|trabalho|casa|outro
    valor: str


class ContatoEndereco(BaseModel):
    tipo: str | None = None
    logradouro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None


class ContatoCanonico(BaseModel):
    """Contato normalizado — independente de provedor."""

    nome: str
    sobrenome: str | None = None
    organizacao: str | None = None
    cargo: str | None = None
    emails: list[ContatoEmail] = Field(default_factory=list)
    telefones: list[ContatoTelefone] = Field(default_factory=list)
    enderecos: list[ContatoEndereco] = Field(default_factory=list)
    notas: str | None = None
    tags: list[str] = Field(default_factory=list)
    municipio_ibge: str | None = None
    uf: str | None = None
    origem: str = "manual"
    chave_dedup: str | None = None
    hash_conteudo: str | None = None

    @property
    def nome_completo(self) -> str:
        return " ".join(p for p in (self.nome, self.sobrenome) if p).strip()


class ContatoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    sobrenome: str | None = None
    organizacao: str | None = None
    cargo: str | None = None
    emails: list[ContatoEmail] = Field(default_factory=list)
    telefones: list[ContatoTelefone] = Field(default_factory=list)
    enderecos: list[ContatoEndereco] = Field(default_factory=list)
    notas: str | None = None
    tags: list[str] = Field(default_factory=list)
    municipio_ibge: str | None = Field(default=None, max_length=7)
    uf: str | None = Field(default=None, max_length=2)


class ContatoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    sobrenome: str | None = None
    organizacao: str | None = None
    cargo: str | None = None
    emails: list[ContatoEmail] | None = None
    telefones: list[ContatoTelefone] | None = None
    enderecos: list[ContatoEndereco] | None = None
    notas: str | None = None
    tags: list[str] | None = None
    municipio_ibge: str | None = Field(default=None, max_length=7)
    uf: str | None = Field(default=None, max_length=2)


class ContatoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    sobrenome: str | None = None
    organizacao: str | None = None
    cargo: str | None = None
    emails: list[ContatoEmail] = Field(default_factory=list)
    telefones: list[ContatoTelefone] = Field(default_factory=list)
    enderecos: list[ContatoEndereco] = Field(default_factory=list)
    notas: str | None = None
    tags: list[str] = Field(default_factory=list)
    municipio_ibge: str | None = None
    uf: str | None = None
    origem: str
    arquivado: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("emails", "telefones", "enderecos", "tags", mode="before")
    @classmethod
    def _lista_vazia(cls, v):
        """Coluna jsonb/array nula no banco vale como lista vazia na resposta."""
        return v if v is not None else []


# ── Integrações ──────────────────────────────────────────────────────────────


class ProvedorInfo(BaseModel):
    """Catálogo de provedores para a tela de conexão."""

    provedor: str
    rotulo: str
    tipo_auth: str  # oauth | senha_app
    disponivel: bool  # credencial de aplicação configurada no painel admin
    instrucoes: str | None = None


class IntegracaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provedor: str
    conta: str
    status: str
    direcao: str
    ultima_sync_em: datetime | None = None
    ultimo_erro: str | None = None
    total_contatos: int = 0
    ativo: bool = True


class ConectarSenhaApp(BaseModel):
    """Conexão por senha de aplicativo (Apple/iCloud e CardDAV genérico)."""

    conta: str = Field(min_length=3, max_length=255, description="Apple ID / usuário")
    senha_app: str = Field(min_length=4, description="senha de app (não é a senha da conta)")
    base_url: str | None = Field(default=None, description="CardDAV genérico: URL do servidor")
    direcao: str = "bidirecional"


class AutorizacaoOAuth(BaseModel):
    url: str
    state: str


class CallbackOAuth(BaseModel):
    provedor: str
    code: str
    state: str | None = None
    redirect_uri: str | None = None
    direcao: str = "bidirecional"


class IntegracaoUpdate(BaseModel):
    direcao: str | None = None
    ativo: bool | None = None


class SyncResultado(BaseModel):
    """Placar de uma sincronização (por integração)."""

    integracao_id: uuid.UUID
    provedor: str
    conta: str
    status: str  # ok | erro | desabilitada
    importados: int = 0
    atualizados_local: int = 0
    exportados: int = 0
    atualizados_remoto: int = 0
    removidos_local: int = 0
    removidos_remoto: int = 0
    conflitos: int = 0
    erro: str | None = None


class ImportacaoVcard(BaseModel):
    conteudo: str = Field(description="conteúdo de um arquivo .vcf")


class ImportacaoResultado(BaseModel):
    importados: int
    atualizados: int
    ignorados: int
