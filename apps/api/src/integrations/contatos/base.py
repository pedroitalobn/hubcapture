"""Interface comum dos provedores de agenda + registry.

Mesmo espírito de `connectors/base.py`: cada provedor (Google People, Microsoft
Graph, CardDAV/iCloud) implementa o mesmo Protocol e se registra; o motor de
sync (`services/contatos_sync.py`) não conhece nenhum deles em particular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ...schemas.contato import ContatoCanonico


@dataclass
class Credencial:
    """Credenciais decifradas de uma conta conectada.

    `dados` é mutável de propósito: quando o provedor renova o access token, ele
    escreve aqui e marca `alterada` — o motor persiste (cifrado) ao final.
    """

    conta: str
    dados: dict = field(default_factory=dict)
    alterada: bool = False

    def atualizar(self, **novos) -> None:
        self.dados.update(novos)
        self.alterada = True


@dataclass
class ContatoExterno:
    """Contato do lado do provedor, já normalizado."""

    id_externo: str
    canonico: ContatoCanonico | None = None
    etag: str | None = None
    removido: bool = False


@dataclass
class PaginaRemota:
    """Resultado de uma leitura do provedor.

    `sync_token` volta para o banco e vira o cursor do próximo delta.
    `completa=True` significa listagem cheia (sem delta): o motor pode inferir
    remoções por ausência; num delta, ausência não é remoção.
    """

    itens: list[ContatoExterno] = field(default_factory=list)
    sync_token: str | None = None
    completa: bool = True


@runtime_checkable
class ProvedorContatos(Protocol):
    provedor_id: str
    rotulo: str
    tipo_auth: str  # 'oauth' | 'senha_app'

    async def disponivel(self) -> bool:
        """True se a credencial de APLICAÇÃO está configurada no painel admin."""
        ...

    async def listar(
        self, cred: Credencial, sync_token: str | None
    ) -> PaginaRemota: ...

    async def criar(
        self, cred: Credencial, canonico: ContatoCanonico
    ) -> ContatoExterno: ...

    async def atualizar(
        self,
        cred: Credencial,
        id_externo: str,
        etag: str | None,
        canonico: ContatoCanonico,
    ) -> ContatoExterno: ...

    async def remover(
        self, cred: Credencial, id_externo: str, etag: str | None
    ) -> None: ...


class ProvedorIndisponivel(Exception):
    """Provedor sem credencial de aplicação/conta — o fluxo degrada, não quebra."""


_registry: dict[str, ProvedorContatos] = {}


def register(provedor: ProvedorContatos) -> ProvedorContatos:
    _registry[provedor.provedor_id] = provedor
    return provedor


def get_provedor(provedor_id: str) -> ProvedorContatos:
    if provedor_id not in _registry:
        raise KeyError(f"provedor de contatos não registrado: {provedor_id!r}")
    return _registry[provedor_id]


def provedores() -> list[ProvedorContatos]:
    return [_registry[k] for k in sorted(_registry)]
