"""Consultas de propostas salvas — as abas do construtor de consultas (§61).

As chaves de `filtros` são as MESMAS dos query params de `GET /proposals`
(mais `municipio`/`fonte`, que na tela são o recorte global). Assim a aba é
literalmente a consulta: executá-la é mandar o objeto como querystring, sem
de-para nenhum entre o que foi salvo e o que a API entende.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IBGE = re.compile(r"^\d{7}$")


class FiltrosConsulta(BaseModel):
    """O recorte guardado pela aba. Campo ausente/vazio = sem aquele filtro."""

    # `forbid`: chave desconhecida é erro na hora de salvar, não lixo que só
    # aparece quando a aba deixa de filtrar o que o gestor montou.
    model_config = ConfigDict(extra="forbid")

    # Município e origem do recurso são recorte GLOBAL do painel (§33/§33b) —
    # aqui eles ficam DENTRO da aba porque é isso que permite "uma aba por
    # município". Vazio = a aba segue o recorte global da barra; preenchido =
    # a aba manda enquanto estiver ativa. Nunca AMPLIA: o RLS e o plano seguem
    # sendo o limite, isto só estreita.
    municipio: list[str] = Field(default_factory=list)
    fonte: list[str] = Field(default_factory=list)
    ano: list[str] = Field(default_factory=list)

    uf: str | None = Field(default=None, min_length=2, max_length=2)
    area: str | None = None
    situacao: str | None = None
    modalidade: str | None = None
    orgao: str | None = None
    natureza_juridica: str | None = None
    natureza_grupo: str | None = Field(default=None, pattern="^(entes_municipais|outros)$")
    qualificacao: str | None = None
    categoria: str | None = None
    mes: str | None = Field(default=None, pattern="^(0[1-9]|1[0-2])$")
    q: str | None = None
    valor_min: Decimal | None = Field(default=None, ge=0)
    valor_max: Decimal | None = Field(default=None, ge=0)
    tipo: str | None = Field(default=None, pattern="^(cadastrada|disponivel)$")
    ordenar: str | None = Field(
        default=None, pattern="^(recentes|prazo|prazo_distante|nome|orgao|valor)$"
    )

    # Curadoria — não são filtros da fonte, são do acervo do próprio gestor.
    so_favoritas: bool = False
    pasta_id: uuid.UUID | None = None

    @field_validator("municipio")
    @classmethod
    def _ibges(cls, v: list[str]) -> list[str]:
        limpos = [c.strip() for c in v if c and c.strip()]
        for c in limpos:
            if not _IBGE.match(c):
                raise ValueError("município deve ser um código IBGE de 7 dígitos")
        return list(dict.fromkeys(limpos))

    @field_validator("fonte", "ano")
    @classmethod
    def _lista_limpa(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(x.strip() for x in v if x and x.strip()))


class ConsultaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    filtros: FiltrosConsulta = Field(default_factory=FiltrosConsulta)


class ConsultaUpdate(BaseModel):
    """PATCH parcial: campo ausente fica como está.

    `filtros` é substituído por INTEIRO quando vem — limpar um filtro é
    mandar o recorte sem ele, e um merge parcial deixaria filtro removido
    grudado na aba.
    """

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    filtros: FiltrosConsulta | None = None
    ordem: int | None = Field(default=None, ge=0)


class ConsultaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str
    filtros: FiltrosConsulta
    ordem: int
    created_at: datetime
    updated_at: datetime | None = None


class ConsultasOrdem(BaseModel):
    """Nova ordem da fileira de abas (ids na sequência desejada)."""

    ids: list[uuid.UUID] = Field(min_length=1)
