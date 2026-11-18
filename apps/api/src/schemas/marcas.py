"""Schemas do white label (§69).

O TEMA nunca é CSS livre: cada campo é um hex validado, um item de catálogo
fechado ou texto curto. É isso que permite ao servidor montar o CSS da marca e
o site injetá-lo sem abrir uma porta de injeção — nada que o dono digita chega
ao navegador como código.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_HEX = re.compile(r"^#[0-9a-f]{6}$")

FORMAS = ("reta", "padrao", "suave", "arredondada", "pilula")
TRACOS_ICONE = ("fino", "regular", "grosso")


def _hex_ou_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if re.fullmatch(r"#?[0-9a-f]{3}", s):  # #abc → #aabbcc
        s = "#" + "".join(c * 2 for c in s.lstrip("#"))
    if not s.startswith("#"):
        s = "#" + s
    if not _HEX.match(s):
        raise ValueError("cor inválida — use hexadecimal #rrggbb")
    return s


def _texto(v: object) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())  # sem quebra de linha nem espaço duplo
    return s or None


class CoresMarca(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # o destaque (chip ativo, foco, progresso, ponto da marca)
    acento: str | None = None
    # o tom escuro (trilho e canvas no tema escuro, banda do e-mail e do PDF)
    escuro: str | None = None
    # a cor de AÇÃO no tema claro (botão, link) — precisa de contraste no branco
    acao: str | None = None

    _hex = field_validator("acento", "escuro", "acao", mode="before")(_hex_ou_none)


class TemaMarca(BaseModel):
    """Tudo que a marca personaliza. Ausente/None = o padrão do Hub Capture."""

    model_config = ConfigDict(extra="forbid")

    nome_exibicao: str | None = Field(default=None, max_length=60)
    nome_assistente: str | None = Field(default=None, max_length=40)
    cores: CoresMarca = Field(default_factory=CoresMarca)
    forma: Literal["reta", "padrao", "suave", "arredondada", "pilula"] = "padrao"
    # chave do catálogo services/marcas.FONTES ("arquivo" = fonte enviada)
    fonte_corpo: str = "inter"
    fonte_titulo: str = "archivo"
    titulos_caixa_alta: bool = True
    icones: Literal["fino", "regular", "grosso"] = "regular"
    icones_cantos: Literal["arredondado", "reto"] = "arredondado"
    # com logo enviado, o nome por extenso ao lado dele é opcional
    nome_com_logo: bool = False

    login_titulo: str | None = Field(default=None, max_length=80)
    login_subtitulo: str | None = Field(default=None, max_length=200)
    login_slogan: str | None = Field(default=None, max_length=120)
    rodape: str | None = Field(default=None, max_length=120)

    _textos = field_validator(
        "nome_exibicao",
        "nome_assistente",
        "login_titulo",
        "login_subtitulo",
        "login_slogan",
        "rodape",
        mode="before",
    )(_texto)

    @field_validator("fonte_corpo", "fonte_titulo")
    @classmethod
    def _fonte_do_catalogo(cls, v: str) -> str:
        from ..services.marcas import FONTES  # catálogo vive no serviço

        chave = (v or "").strip().lower()
        if chave not in FONTES:
            raise ValueError(f"fonte desconhecida: {v}")
        return chave


class AssetInfo(BaseModel):
    tipo: str
    url: str
    content_type: str
    tamanho: int
    nome_arquivo: str | None = None


class BrandingRead(BaseModel):
    """O que o SITE precisa para se vestir — público, resolvido pelo host."""

    personalizada: bool  # False = Hub Capture
    id: uuid.UUID | None = None
    slug: str | None = None
    nome: str
    assistente: str
    tema: TemaMarca
    css: str
    fontes_urls: list[str] = []
    logo_url: str | None = None
    logo_escuro_url: str | None = None
    icone_url: str | None = None
    login_imagem_url: str | None = None
    cadastro_aberto: bool = True
    cor_tema_claro: str
    cor_tema_escuro: str


class PreviewRequest(BaseModel):
    tema: TemaMarca
    marca_id: uuid.UUID | None = None  # usa as fontes enviadas dessa marca


class PreviewRead(BaseModel):
    css: str
    fontes_urls: list[str] = []
    avisos: list[str] = []


class ProvisionamentoHost(BaseModel):
    host: str
    status: str  # ok | manual | erro | removido
    detalhe: str | None = None
    em: str | None = None


class MarcaRead(BaseModel):
    id: uuid.UUID
    slug: str
    nome: str
    ativo: bool
    cadastro_aberto: bool
    dono_id: uuid.UUID | None = None
    dono_email: str | None = None
    plano_id: uuid.UUID | None = None
    tema: TemaMarca
    host_padrao: str  # marca.hubcapture.com.br
    url: str  # endereço em uso (domínio próprio ativo ou subdomínio)
    dominio: str | None = None
    dominio_status: str | None = None
    dominio_detalhe: str | None = None
    dominio_verificado_em: datetime | None = None
    cname_alvo: str
    provisionamento: list[ProvisionamentoHost] = []
    assets: list[AssetInfo] = []
    membros: int = 0
    created_at: datetime | None = None


class MarcaCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=63)
    nome: str = Field(min_length=2, max_length=120)
    dono_email: EmailStr | None = None
    plano_id: uuid.UUID | None = None
    tema: TemaMarca | None = None


class MarcaUpdate(BaseModel):
    """Campos do DONO: nome, tema, cadastro aberto. Os de ADMIN (slug, ativo,
    dono, plano) são recusados com 403 para quem não é superuser."""

    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, min_length=2, max_length=120)
    tema: TemaMarca | None = None
    cadastro_aberto: bool | None = None
    # admin
    slug: str | None = Field(default=None, min_length=3, max_length=63)
    ativo: bool | None = None
    dono_email: EmailStr | None = None
    remover_dono: bool | None = None
    plano_id: uuid.UUID | None = None
    remover_plano: bool | None = None


class DominioUpdate(BaseModel):
    dominio: str | None = Field(default=None, max_length=253)


class MembroMarca(BaseModel):
    id: uuid.UUID
    email: str
    nome: str | None = None
    papel: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class ConviteMarcaCreate(BaseModel):
    email: EmailStr
    papel: str | None = None
    expires_em_dias: int | None = Field(default=None, ge=1, le=60)  # padrão 7


class OpcaoCatalogo(BaseModel):
    chave: str
    rotulo: str
    detalhe: str | None = None


class OpcoesMarca(BaseModel):
    fontes: list[OpcaoCatalogo]
    formas: list[OpcaoCatalogo]
    icones: list[OpcaoCatalogo]
    tipos_asset: list[OpcaoCatalogo]
    dominio_base: str
    provisionador: str
