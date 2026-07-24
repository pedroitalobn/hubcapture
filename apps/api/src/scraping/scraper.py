"""Facade de scraping — Crawl4AI + Firecrawl com fallback (degradação graciosa).

Os connectors chamam `get_scraper()` e nunca um provider direto. A ordem vem da
config `scraping_provider` (painel admin): 'auto' (padrão) prefere Crawl4AI
(self-hosted, sem custo por página) e cai para Firecrawl; 'crawl4ai'/'firecrawl'
apenas invertem a preferência — o outro provider segue como fallback. Um provider
sem credencial fica fora da rodada; se nenhum estiver configurado, levanta
`ScraperNotConfigured` (tratado pelos serviços → sync_runs).

O resultado carrega `_scraper` (nome do provider que respondeu) p/ proveniência.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..services import config as config_service
from .crawl4ai import Crawl4aiClient, get_crawl4ai
from .firecrawl import FirecrawlClient, get_firecrawl


class ScraperNotConfigured(RuntimeError):
    """Nenhum provider de scraping configurado (painel admin)."""


class ScrapingProvider(Protocol):
    async def is_enabled(self) -> bool: ...
    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]: ...
    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]: ...


class Scraper:
    def __init__(
        self,
        crawl4ai: ScrapingProvider | None = None,
        firecrawl: ScrapingProvider | None = None,
        provider: str | None = None,
    ) -> None:
        self._crawl4ai: ScrapingProvider = crawl4ai or get_crawl4ai()
        self._firecrawl: ScrapingProvider = firecrawl or get_firecrawl()
        self._provider_override = provider

    async def _preferencia(self) -> str:
        if self._provider_override:
            return self._provider_override
        try:
            valor = await config_service.resolver("scraping_provider")
        except Exception:
            valor = None
        return (valor or "auto").lower()

    async def _providers(self) -> list[tuple[str, ScrapingProvider]]:
        """Providers habilitados, na ordem de preferência."""
        ordem = [("crawl4ai", self._crawl4ai), ("firecrawl", self._firecrawl)]
        if await self._preferencia() == "firecrawl":
            ordem.reverse()
        habilitados = []
        for nome, prov in ordem:
            if await prov.is_enabled():
                habilitados.append((nome, prov))
        return habilitados

    async def is_enabled(self) -> bool:
        return bool(await self._providers())

    async def _tentar(self, metodo: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        providers = await self._providers()
        if not providers:
            raise ScraperNotConfigured(
                "Nenhum scraper configurado — defina crawl4ai_base_url ou "
                "firecrawl_api_key no painel admin"
            )
        ultimo_erro: Exception | None = None
        for nome, prov in providers:
            try:
                resultado = await getattr(prov, metodo)(*args, **kwargs)
                resultado = dict(resultado or {})
                resultado["_scraper"] = nome
                return resultado
            except Exception as exc:  # provider caiu → tenta o próximo (fallback)
                ultimo_erro = exc
        assert ultimo_erro is not None
        raise ultimo_erro

    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        return await self._tentar("scrape", url, formats)

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        return await self._tentar("extract", url, schema, prompt)


def get_scraper() -> Scraper:
    return Scraper()


__all__ = [
    "Scraper",
    "ScraperNotConfigured",
    "get_scraper",
    "Crawl4aiClient",
    "FirecrawlClient",
]
