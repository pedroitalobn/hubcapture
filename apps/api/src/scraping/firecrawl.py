"""Cliente Firecrawl — scraping para a coleta combinada (API + scraping → merge).

A credencial e a base URL vêm do painel admin (config runtime) com fallback para
o `.env`. Desabilitado quando não há chave configurada — os connectors degradam
para só-API (a coleta combinada trata como fallback).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..services import config as config_service

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class FirecrawlNotConfigured(RuntimeError):
    """Levantado quando o scraping é solicitado sem credencial configurada."""


class FirecrawlClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key_override = api_key
        self._base_url_override = base_url

    async def _key(self) -> str | None:
        if self._api_key_override is not None:
            return self._api_key_override or None
        return await config_service.resolver("firecrawl_api_key")

    async def _base(self) -> str:
        if self._base_url_override:
            return self._base_url_override
        return (await config_service.resolver("firecrawl_base_url")) or "https://api.firecrawl.dev"

    async def is_enabled(self) -> bool:
        return bool(await self._key())

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._key()}",
            "Content-Type": "application/json",
        }

    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        if not await self.is_enabled():
            raise FirecrawlNotConfigured("Firecrawl não configurado (painel admin)")
        payload = {"url": url, "formats": formats or ["markdown"]}
        async with httpx.AsyncClient(base_url=await self._base(), timeout=TIMEOUT) as client:
            resp = await client.post("/v1/scrape", json=payload, headers=await self._headers())
            resp.raise_for_status()
        return resp.json().get("data", {})

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        if not await self.is_enabled():
            raise FirecrawlNotConfigured("Firecrawl não configurado (painel admin)")
        payload: dict[str, Any] = {"urls": [url], "schema": schema}
        if prompt:
            payload["prompt"] = prompt
        async with httpx.AsyncClient(base_url=await self._base(), timeout=TIMEOUT) as client:
            resp = await client.post("/v1/extract", json=payload, headers=await self._headers())
            resp.raise_for_status()
        return resp.json().get("data", {})


def get_firecrawl() -> FirecrawlClient:
    return FirecrawlClient()
