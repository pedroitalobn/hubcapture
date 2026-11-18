"""Identidade de marca em uso (white label, §69) — quem ASSINA o que sai do Hub.

O site resolve a marca pelo HOST (o que a barra de endereço diz). Fora do site
— e-mail, espelho em PDF, push, WhatsApp, Copiloto — não há host: quem assina é
a marca do USUÁRIO (`usuarios.marca_id`). Essas superfícies não recebem a marca
por parâmetro (seriam dezenas de assinaturas mudando): leem a identidade em uso
deste `ContextVar`, que o chamador liga com `usar()` em volta do envio.

Sem nada ligado, vale a identidade PADRÃO — o Hub Capture —, então todo código
que ainda não conhece white label continua saindo exatamente como antes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

NOME_PADRAO = "Hub Capture"
ASSISTENTE_PADRAO = "Copiloto"


@dataclass(frozen=True)
class Identidade:
    """O que uma superfície externa precisa saber da marca para se vestir.

    Cores já VALIDADAS (hex `#rrggbb`) — quem monta a identidade é o serviço de
    marcas, a partir do tema sanitizado. `padrao=True` é o Hub Capture: e-mail e
    PDF mantêm a arte original (gradiente lime→aqua) em vez de cor sólida.
    """

    nome: str = NOME_PADRAO
    assistente: str = ASSISTENTE_PADRAO
    acento: str = "#43cf9b"
    escuro: str = "#031918"
    acao: str = "#1c6555"
    url_base: str | None = None  # https://marca.hubcapture.com.br (sem barra final)
    logo_url: str | None = None  # absoluta — e-mail não resolve caminho relativo
    logo_bytes: bytes | None = field(default=None, repr=False)  # PDF desenha o logo
    marca_id: str | None = None
    padrao: bool = True

    @property
    def assinatura(self) -> str:
        """Prefixo curto de push/WhatsApp ("Hub Capture · …")."""
        return self.nome


PADRAO = Identidade()

_atual: ContextVar[Identidade] = ContextVar("identidade_marca", default=PADRAO)


def atual() -> Identidade:
    return _atual.get()


@contextmanager
def usar(identidade: Identidade | None) -> Iterator[Identidade]:
    """Liga a identidade dentro do bloco (None = padrão) e restaura ao sair."""
    token = _atual.set(identidade or PADRAO)
    try:
        yield _atual.get()
    finally:
        _atual.reset(token)
