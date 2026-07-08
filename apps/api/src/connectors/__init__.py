"""Connectors. Importar as fontes aqui registra-as no registry."""

from . import transferegov_ff  # noqa: F401  (efeito colateral: registra o connector)
from .base import RawRecord, available_sources, get_connector, register

__all__ = ["RawRecord", "get_connector", "register", "available_sources"]
