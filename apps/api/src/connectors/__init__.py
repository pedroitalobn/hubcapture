"""Connectors. Importar as fontes aqui registra-as no registry."""

from . import (
    caixa,  # noqa: F401  (obras — CAIXA/SIORB OGU+APF)
    emendas,  # noqa: F401  (recebidos — Emendas)
    fnde,  # noqa: F401  (educação — API + scraping)
    fns,  # noqa: F401  (saúde — scraping)
    fpm,  # noqa: F401  (recebidos — FPM)
    serpro,  # noqa: F401  (enrichment)
    siconfi,  # noqa: F401  (conformidade — CAUC/CAPAG CSV)
    simec,  # noqa: F401  (obras — educação FNDE/MEC)
    sismob,  # noqa: F401  (obras — saúde MS)
    transferegov_disc,  # noqa: F401  (discricionárias — CSV)
    transferegov_esp,  # noqa: F401  (especiais — API pública + fallback)
    transferegov_ff,  # noqa: F401  (fundo a fundo — API)
    transferegov_voluntarias,  # noqa: F401  (voluntárias/convênios — API pública)
)
from .base import RawRecord, available_sources, get_connector, register

__all__ = ["RawRecord", "get_connector", "register", "available_sources"]
