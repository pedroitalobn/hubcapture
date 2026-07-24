"""Registry de connectors + scraping (Firecrawl/Crawl4AI/facade) sem credencial."""

from __future__ import annotations

import pytest

from src.connectors import available_sources, get_connector
from src.scraping.crawl4ai import Crawl4aiClient, Crawl4aiNotConfigured
from src.scraping.firecrawl import FirecrawlClient, FirecrawlNotConfigured
from src.scraping.scraper import Scraper, ScraperNotConfigured

FONTES_ESPERADAS = {
    "transferegov_ff",
    "transferegov_esp",
    "transferegov_disc",
    "transferegov_voluntarias",
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


async def test_crawl4ai_desabilitado_sem_base_url() -> None:
    c4 = Crawl4aiClient(base_url="")
    assert await c4.is_enabled() is False
    with pytest.raises(Crawl4aiNotConfigured):
        await c4.scrape("https://exemplo.gov.br")


# ── Facade de scraping (fallback entre providers) ───────────────────────────


class _StubProvider:
    def __init__(self, enabled: bool = True, falha: bool = False, nome: str = "stub"):
        self._enabled = enabled
        self._falha = falha
        self._nome = nome

    async def is_enabled(self) -> bool:
        return self._enabled

    async def scrape(self, url, formats=None):
        if self._falha:
            raise RuntimeError(f"{self._nome} caiu")
        return {"markdown": f"md-{self._nome}"}

    async def extract(self, url, schema, prompt=None):
        if self._falha:
            raise RuntimeError(f"{self._nome} caiu")
        return {"dados": self._nome}


async def test_scraper_sem_provider_levanta() -> None:
    s = Scraper(
        crawl4ai=_StubProvider(enabled=False),
        firecrawl=_StubProvider(enabled=False),
        provider="auto",
    )
    assert await s.is_enabled() is False
    with pytest.raises(ScraperNotConfigured):
        await s.scrape("https://exemplo.gov.br")


async def test_scraper_prefere_crawl4ai_no_auto() -> None:
    s = Scraper(
        crawl4ai=_StubProvider(nome="crawl4ai"),
        firecrawl=_StubProvider(nome="firecrawl"),
        provider="auto",
    )
    resultado = await s.scrape("https://exemplo.gov.br")
    assert resultado["markdown"] == "md-crawl4ai"
    assert resultado["_scraper"] == "crawl4ai"


async def test_scraper_fallback_quando_preferido_cai() -> None:
    s = Scraper(
        crawl4ai=_StubProvider(nome="crawl4ai", falha=True),
        firecrawl=_StubProvider(nome="firecrawl"),
        provider="auto",
    )
    resultado = await s.extract("https://exemplo.gov.br", {"type": "object"})
    assert resultado["dados"] == "firecrawl"
    assert resultado["_scraper"] == "firecrawl"


async def test_scraper_preferencia_firecrawl_inverte_ordem() -> None:
    s = Scraper(
        crawl4ai=_StubProvider(nome="crawl4ai"),
        firecrawl=_StubProvider(nome="firecrawl"),
        provider="firecrawl",
    )
    resultado = await s.scrape("https://exemplo.gov.br")
    assert resultado["_scraper"] == "firecrawl"


async def test_scraper_propaga_erro_quando_todos_caem() -> None:
    s = Scraper(
        crawl4ai=_StubProvider(nome="crawl4ai", falha=True),
        firecrawl=_StubProvider(nome="firecrawl", falha=True),
        provider="auto",
    )
    with pytest.raises(RuntimeError, match="firecrawl caiu"):
        await s.scrape("https://exemplo.gov.br")
