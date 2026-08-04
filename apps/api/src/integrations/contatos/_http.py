"""HTTP dos provedores de agenda: retry em 5xx/transporte, erro claro em 4xx.

Mesma política do `connectors/_http.py`, mas com verbos arbitrários (os provedores
usam PATCH/PUT/DELETE e o CardDAV usa PROPFIND/REPORT) e headers por chamada.
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


class ProvedorClientError(Exception):
    """4xx do provedor (token inválido, payload recusado) — não é retry."""

    def __init__(self, mensagem: str, status: int) -> None:
        super().__init__(mensagem)
        self.status = status

    @property
    def auth_expirada(self) -> bool:
        return self.status in (401, 403)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json: dict | None = None,
    data: dict[str, str] | None = None,
    content: str | None = None,
    auth: tuple[str, str] | None = None,
    follow_redirects: bool = True,
) -> httpx.Response:
    # follow_redirects=False é usado pelo CardDAV: o httpx descarta o header de
    # autenticação em redirect entre hosts (iCloud manda p{n}-contacts...), então
    # aquele provedor refaz o salto com a credencial na mão.
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=follow_redirects) as client:
        resp = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            data=data,
            content=content,
            auth=auth,
        )
    if 400 <= resp.status_code < 500:
        raise ProvedorClientError(
            f"{method} {url} → {resp.status_code}: {resp.text[:300]}", resp.status_code
        )
    resp.raise_for_status()  # 5xx → HTTPStatusError → retry
    return resp


async def request_json(method: str, url: str, **kwargs) -> dict:
    resp = await request(method, url, **kwargs)
    if not resp.content or resp.status_code == 204:
        return {}
    return resp.json()
