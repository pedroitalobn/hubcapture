"""Helper HTTP compartilhado pelos connectors (retry/backoff + erro de cliente).

Mesma política do `transferegov_ff`: retry 3x com backoff exponencial em
5xx/timeout/erro de transporte; 4xx vira ConnectorClientError (não é retry).

**Egresso alternativo (§ ver `_egress`).** Fonte que bloqueia o IP deste servidor
— 403 com desafio da Cloudflare (TransfereGov) ou timeout de borda (Ministério
da Saúde) — não é erro de rota e não se resolve com retry: as três tentativas
levam ao mesmo 403. Nesses dois casos, e SÓ neles, a mesma URL é buscada por um
provider com egresso próprio e o JSON oficial volta por lá. 403 comum do
PostgREST (filtro/coluna inválida) continua sendo `ConnectorClientError`, senão
um bug de query viraria custo de scraping e sumiria do log.
"""

from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import _egress

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ConnectorClientError(Exception):
    """Erro 4xx da fonte (filtro/rota inválida) — não deve ser retry."""


class _Desafiado(Exception):
    """403/503 com assinatura de desafio de bot — vai para o egresso."""


def url_absoluta(base_url: str, endpoint: str, params: dict[str, str]) -> str:
    """A URL que o httpx montaria — mesma regra de merge do `AsyncClient`.

    O merge do httpx CONCATENA (base + endpoint sem a barra inicial); não é o
    join da RFC 3986, que descartaria o último segmento da base. Replicado aqui
    para o egresso pedir exatamente a URL que falhou.
    """
    base = httpx.URL(base_url)
    caminho = base.raw_path + endpoint.encode().lstrip(b"/")
    return str(base.copy_with(raw_path=caminho).copy_merge_params(params))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def _direto(
    base_url: str,
    endpoint: str,
    params: dict[str, str],
    headers: dict[str, str] | None = None,
) -> list | dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
        resp = await client.get(
            endpoint,
            params=params,
            headers={"Accept": "application/json", **(headers or {})},
        )
        if _egress.e_desafio(resp):
            raise _Desafiado(f"{resp.status_code} com desafio de bot")
        if 400 <= resp.status_code < 500:
            raise ConnectorClientError(f"{endpoint} {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()  # 5xx → HTTPStatusError → retry
        return resp.json()


async def get_json(
    base_url: str,
    endpoint: str,
    params: dict[str, str],
    headers: dict[str, str] | None = None,
) -> list | dict:
    url = url_absoluta(base_url, endpoint, params)
    if _egress.bloqueado(url):
        return await _egress.get_json(url)
    try:
        dados = await _direto(base_url, endpoint, params, headers)
    except (_Desafiado, httpx.TransportError) as exc:
        log.warning("fonte bloqueou o IP deste servidor (%s: %s) — tentando egresso", url, exc)
        _egress.marcar_bloqueado(url)
        try:
            return await _egress.get_json(url)
        except Exception:
            _egress.desmarcar(url)  # egresso falhou: não deixa o host marcado
            raise
    _egress.desmarcar(url)
    return dados
