"""Cliente Firecrawl — scraping para a coleta combinada (API + scraping → merge).

Usado pelos connectors que enriquecem/fazem fallback por scraping (FNS, FNDE,
Transf. Especiais). Desabilitado quando não há `FIRECRAWL_API_KEY` — nesse caso
os connectors degradam para só-API (a coleta combinada trata isso como fallback).

Docs: POST {base}/v1/scrape  ·  POST {base}/v1/extract (structured, com schema).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..core.config import settings

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class FirecrawlNotConfigured(RuntimeError):
    """Levantado quando o scraping é solicitado sem FIRECRAWL_API_KEY."""


class FirecrawlClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.firecrawl_api_key
        self.base_url = base_url or settings.firecrawl_base_url

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        """Extrai conteúdo de uma URL (markdown por padrão). Retorna `data` do Firecrawl."""
        if not self.enabled:
            raise FirecrawlNotConfigured("FIRECRAWL_API_KEY não configurada")
        payload = {"url": url, "formats": formats or ["markdown"]}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT) as client:
            resp = await client.post("/v1/scrape", json=payload, headers=self._headers())
            resp.raise_for_status()
            body = resp.json()
        return body.get("data", body)

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        """Extração estruturada guiada por JSON Schema (quando a fonte é só HTML)."""
        if not self.enabled:
            raise FirecrawlNotConfigured("FIRECRAWL_API_KEY não configurada")
        payload: dict[str, Any] = {"urls": [url], "schema": schema}
        if prompt:
            payload["prompt"] = prompt
        async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT) as client:
            resp = await client.post("/v1/extract", json=payload, headers=self._headers())
            resp.raise_for_status()
            body = resp.json()
        return body.get("data", body)


def get_firecrawl() -> FirecrawlClient:
    return FirecrawlClient()
