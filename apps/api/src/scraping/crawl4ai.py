"""Cliente Crawl4AI — scraping self-hosted (servidor Docker do Crawl4AI).

Fala com a API HTTP do servidor Crawl4AI (`docker run unclecode/crawl4ai`):
`POST /md` devolve o markdown "fit" da página (renderizada com browser headless,
essencial p/ painéis JS como o dd-publico do SERPRO) e `POST /llm/{url}` responde
perguntas/extração sobre a página. Rotas isoladas em constantes p/ calibração.

Provider-opcional como o Firecrawl: sem `crawl4ai_base_url` configurada (painel
admin ou .env) o cliente degrada — `is_enabled()` False e chamadas levantam
`Crawl4aiNotConfigured` (a facade `scraping.scraper` trata o fallback).
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from ..services import config as config_service

TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# ── Rotas do servidor Crawl4AI (calibrar conforme a versão do container) ────
MD_ROUTE = "/md"  # POST {"url", "f": "fit"} → {"markdown": ...}
LLM_ROUTE = "/llm"  # GET /llm/{url}?q=... → {"answer": ...}
HEALTH_ROUTE = "/health"


class Crawl4aiNotConfigured(RuntimeError):
    """Levantado quando o scraping é solicitado sem servidor configurado."""


class Crawl4aiClient:
    def __init__(self, base_url: str | None = None, api_token: str | None = None) -> None:
        self._base_url_override = base_url
        self._api_token_override = api_token

    async def _base(self) -> str | None:
        if self._base_url_override is not None:
            return self._base_url_override or None
        return await config_service.resolver("crawl4ai_base_url")

    async def _token(self) -> str | None:
        if self._api_token_override is not None:
            return self._api_token_override or None
        return await config_service.resolver("crawl4ai_api_token")

    async def is_enabled(self) -> bool:
        return bool(await self._base())

    async def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = await self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _require_base(self) -> str:
        base = await self._base()
        if not base:
            raise Crawl4aiNotConfigured("Crawl4AI não configurado (painel admin)")
        return base

    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        """Markdown da página renderizada (mesmo shape do Firecrawl: {'markdown': ...})."""
        base = await self._require_base()
        async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT) as client:
            resp = await client.post(
                MD_ROUTE, json={"url": url, "f": "fit"}, headers=await self._headers()
            )
            resp.raise_for_status()
        data = resp.json()
        return {"markdown": data.get("markdown") or data.get("result") or ""}

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        """Extração estruturada via a rota LLM do servidor (responde JSON do schema)."""
        base = await self._require_base()
        pergunta = (
            (prompt or "Extraia os dados da página.")
            + " Responda SOMENTE com JSON válido seguindo este JSON Schema: "
            + json.dumps(schema, ensure_ascii=False)
        )
        async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{LLM_ROUTE}/{quote(url, safe='')}",
                params={"q": pergunta},
                headers=await self._headers(),
            )
            resp.raise_for_status()
        answer = resp.json().get("answer", "")
        return _parse_json_answer(answer)

    async def health_check(self) -> bool:
        try:
            base = await self._require_base()
            async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT) as client:
                resp = await client.get(HEALTH_ROUTE)
                return resp.status_code == 200
        except Exception:
            return False


def _parse_json_answer(answer: str) -> dict[str, Any]:
    """Extrai o objeto JSON da resposta do LLM (tolerante a cercas de código)."""
    if isinstance(answer, dict):
        return answer
    texto = str(answer).strip()
    match = re.search(r"\{.*\}", texto, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_crawl4ai() -> Crawl4aiClient:
    return Crawl4aiClient()
