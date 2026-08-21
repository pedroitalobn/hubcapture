"""Facade de scraping — quatro providers, do mais barato ao mais caro.

Os connectors chamam `get_scraper()` e nunca um provider direto. A ordem padrão
('auto') é deliberada — instalação nova precisa extrair dado SEM ninguém ter
provisionado nada:

  1. `crawl4ai_local`  — biblioteca no próprio processo (extra `scraping`)
  2. `playwright`      — Chromium headless local, sem dependência do Crawl4AI
  3. `crawl4ai`        — servidor Crawl4AI remoto (`crawl4ai_base_url`)
  4. `firecrawl`       — serviço pago (`firecrawl_api_key`)

`scraping_provider` (painel admin) promove um provider ao topo; os demais seguem
na rodada como fallback. Provider sem credencial/pacote fica de fora; se nenhum
estiver disponível, levanta `ScraperNotConfigured` (os serviços registram o
incidente em `sync_runs` — nunca some silenciosamente).

O resultado carrega `_scraper` (nome do provider que respondeu) p/ proveniência.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..services import config as config_service
from .crawl4ai import Crawl4aiClient, get_crawl4ai
from .crawl4ai_local import Crawl4aiLocalClient, get_crawl4ai_local
from .firecrawl import FirecrawlClient, get_firecrawl
from .playwright import PlaywrightClient, get_playwright


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
        crawl4ai_local: ScrapingProvider | None = None,
        playwright: ScrapingProvider | None = None,
    ) -> None:
        self._crawl4ai: ScrapingProvider = crawl4ai or get_crawl4ai()
        self._firecrawl: ScrapingProvider = firecrawl or get_firecrawl()
        self._crawl4ai_local: ScrapingProvider = crawl4ai_local or get_crawl4ai_local()
        self._playwright: ScrapingProvider = playwright or get_playwright()
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
        ordem: list[tuple[str, ScrapingProvider]] = [
            ("crawl4ai_local", self._crawl4ai_local),
            ("playwright", self._playwright),
            ("crawl4ai", self._crawl4ai),
            ("firecrawl", self._firecrawl),
        ]
        preferido = await self._preferencia()
        if preferido != "auto":
            # o escolhido vai para o topo; os outros continuam como fallback
            ordem.sort(key=lambda item: 0 if item[0] == preferido else 1)
        habilitados = []
        for nome, prov in ordem:
            if await prov.is_enabled():
                habilitados.append((nome, prov))
        return habilitados

    async def is_enabled(self) -> bool:
        return bool(await self._providers())

    async def _tentar(self, metodo: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        providers = await self._providers()
        # Host que recusa o IP deste servidor (ver connectors/_egress): browser
        # LOCAL sai pelo mesmo IP e só queima o timeout — os providers remotos
        # (crawl4ai remoto, firecrawl) vão para a frente. Sem isso cada coleta
        # do FNS pagava ~2 min de timeouts antes de chegar em quem responde.
        url = args[0] if args and isinstance(args[0], str) else None
        if url and providers:
            from ..connectors import _egress  # import local: evita ciclo no boot

            if _egress.bloqueado(url):
                remotos = {"crawl4ai", "firecrawl"}
                providers.sort(key=lambda item: 0 if item[0] in remotos else 1)
        if not providers:
            raise ScraperNotConfigured(
                "Nenhum scraper disponível — instale o extra 'scraping' "
                "(uv sync --extra scraping) para o browser local, ou defina "
                "crawl4ai_base_url/firecrawl_api_key no painel admin"
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


#: nomes aceitos em `scraping_provider` (painel admin)
PROVIDERS = ("auto", "crawl4ai_local", "playwright", "crawl4ai", "firecrawl")

__all__ = [
    "PROVIDERS",
    "Scraper",
    "ScraperNotConfigured",
    "get_scraper",
    "Crawl4aiClient",
    "Crawl4aiLocalClient",
    "FirecrawlClient",
    "PlaywrightClient",
]
