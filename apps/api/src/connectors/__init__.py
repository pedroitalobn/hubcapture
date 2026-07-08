"""Connectors. Importar as fontes aqui registra-as no registry."""

from . import (
    emendas,  # noqa: F401  (recebidos — Emendas)
    fnde,  # noqa: F401  (educação — API + scraping)
    fns,  # noqa: F401  (saúde — scraping)
    fpm,  # noqa: F401  (recebidos — FPM)
    serpro,  # noqa: F401  (enrichment)
    transferegov_disc,  # noqa: F401  (discricionárias — CSV)
    transferegov_esp,  # noqa: F401  (especiais — API + fallback)
    transferegov_ff,  # noqa: F401  (fundo a fundo — API)
)
from .base import RawRecord, available_sources, get_connector, register

__all__ = ["RawRecord", "get_connector", "register", "available_sources"]
