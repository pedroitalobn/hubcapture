"""Provedores de agenda de contatos — importar aqui registra no registry.

Ordem/registro no molde de `connectors/__init__.py`: importar o pacote basta
para `get_provedor(...)`/`provedores()` enxergarem todos.
"""

from . import carddav, google, microsoft  # noqa: F401  (efeito colateral: register)
from .base import (
    ContatoExterno,
    Credencial,
    PaginaRemota,
    ProvedorContatos,
    ProvedorIndisponivel,
    get_provedor,
    provedores,
    register,
)

__all__ = [
    "ContatoExterno",
    "Credencial",
    "PaginaRemota",
    "ProvedorContatos",
    "ProvedorIndisponivel",
    "get_provedor",
    "provedores",
    "register",
]
