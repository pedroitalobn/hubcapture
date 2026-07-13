"""Registry de connectors + comportamento do Firecrawl sem credencial."""

from __future__ import annotations

import pytest

from src.connectors import available_sources, get_connector
from src.scraping.firecrawl import FirecrawlClient, FirecrawlNotConfigured

FONTES_ESPERADAS = {
    "transferegov_ff",
    "transferegov_esp",
    "transferegov_disc",
    "fns",
    "fnde",
    "serpro",
    "fpm",
    "emendas",
}


def test_todas_as_fontes_registradas() -> None:
    assert FONTES_ESPERADAS.issubset(set(available_sources()))
    for f in FONTES_ESPERADAS:
        c = get_connector(f)
        assert c.source_id == f


def test_get_connector_desconhecido_levanta() -> None:
    with pytest.raises(KeyError):
        get_connector("inexistente")


async def test_firecrawl_desabilitado_sem_key() -> None:
    fc = FirecrawlClient(api_key="")
    assert await fc.is_enabled() is False
    with pytest.raises(FirecrawlNotConfigured):
        await fc.scrape("https://exemplo.gov.br")
