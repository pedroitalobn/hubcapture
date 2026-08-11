"""Schemas do andamento (linha do tempo) da proposta."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from .emenda import EmendaColeta
from .parecer import ParecerColeta

# tipos de evento — o front rotula e escolhe o ícone por aqui
TIPOS = ("proposta", "parecer", "prazo", "pendencia", "vigencia", "atualizacao")


class EventoAndamento(BaseModel):
    """Um fato datado da tramitação.

    `futuro` separa o que JÁ aconteceu do que ainda vai vencer: os dois entram
    na mesma linha do tempo, mas um prazo à frente é compromisso, não histórico.
    """

    data: date | None = None
    tipo: str
    titulo: str
    detalhe: str | None = None
    ator: str | None = None
    tom: str = "neutral"  # ok | warn | danger | neutral
    valor: Decimal | None = None
    texto: str | None = None
    url: str | None = None
    futuro: bool = False


class AndamentoColeta(BaseModel):
    """Estado honesto de cada fonte que alimenta a linha do tempo."""

    pareceres: ParecerColeta | None = None
    emendas: EmendaColeta | None = None


class AndamentoPagina(BaseModel):
    itens: list[EventoAndamento] = []
    numero_plano_trabalho: str | None = None
    coleta: AndamentoColeta = AndamentoColeta()
