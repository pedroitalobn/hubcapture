"""Helper HTTP compartilhado pelos connectors (retry/backoff + erro de cliente).

Mesma política do `transferegov_ff`: retry 3x com backoff exponencial em
5xx/timeout/erro de transporte; 4xx vira ConnectorClientError (não é retry).
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ConnectorClientError(Exception):
    """Erro 4xx da fonte (filtro/rota inválida) — não deve ser retry."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def get_json(base_url: str, endpoint: str, params: dict[str, str]) -> list | dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
        resp = await client.get(
            endpoint, params=params, headers={"Accept": "application/json"}
        )
        if 400 <= resp.status_code < 500:
            raise ConnectorClientError(f"{endpoint} {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()  # 5xx → HTTPStatusError → retry
        return resp.json()
