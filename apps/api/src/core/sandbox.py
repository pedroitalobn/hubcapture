"""Modo sandbox (§67): nenhuma chamada HTTP sai do processo.

O sandbox é um deploy separado onde parceiros testam a integração. Ele não
pode tocar o mundo de verdade: nada de coleta nas fontes do governo (gasta CPU
do mesmo VPS da produção e não tem o que buscar — os dados são fictícios),
nada de e-mail/WhatsApp/push para pessoas reais, nada de IA paga.

O código tem dezenas de `httpx.AsyncClient` espalhados (um por connector), sem
uma borda única. Em vez de lembrar de cada um, `instalar_bloqueio()` intercepta
o `send` do httpx na CLASSE: qualquer requisição a host que não esteja na lista
falha na hora com `SaidaBloqueadaSandbox` — uma `httpx.ConnectError`, então
todo tratamento de "fonte fora do ar" que já existe a absorve (vira incidente
em `sync_runs`, nunca 500). Os pontos com regra própria (e-mail por SMTP, que
não é httpx; a busca ao vivo; o 1º sync) também checam `settings.sandbox`.

Só é instalado com SANDBOX=true. Transportes em memória (ASGITransport,
MockTransport — os testes) não são afetados: não saem do processo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from .config import settings

log = logging.getLogger("hubcapture.sandbox")

_LOCAIS = {"localhost", "127.0.0.1", "::1"}


class SaidaBloqueadaSandbox(httpx.ConnectError):
    """Chamada externa recusada porque o processo está em modo sandbox."""


def hosts_permitidos() -> set[str]:
    extras = {h.strip().lower() for h in settings.sandbox_hosts_permitidos.split(",")}
    return _LOCAIS | {h for h in extras if h}


def host_permitido(host: str | None) -> bool:
    return (host or "").lower() in hosts_permitidos()


def _transporte_interno(cliente: httpx.AsyncClient | httpx.Client) -> bool:
    transporte = getattr(cliente, "_transport", None)
    return isinstance(transporte, httpx.ASGITransport | httpx.MockTransport | httpx.WSGITransport)


def instalar_bloqueio() -> Callable[[], None]:
    """Intercepta o httpx. Devolve a função que desfaz (testes)."""
    envio_async = httpx.AsyncClient.send
    envio_sync = httpx.Client.send

    async def send_async(self, request: httpx.Request, *args, **kwargs):  # noqa: ANN001, ANN202
        if not _transporte_interno(self) and not host_permitido(request.url.host):
            log.info("sandbox: chamada externa bloqueada (%s)", request.url.host)
            raise SaidaBloqueadaSandbox(
                f"sandbox: chamada externa bloqueada ({request.url.host})", request=request
            )
        return await envio_async(self, request, *args, **kwargs)

    def send_sync(self, request: httpx.Request, *args, **kwargs):  # noqa: ANN001, ANN202
        if not _transporte_interno(self) and not host_permitido(request.url.host):
            raise SaidaBloqueadaSandbox(
                f"sandbox: chamada externa bloqueada ({request.url.host})", request=request
            )
        return envio_sync(self, request, *args, **kwargs)

    httpx.AsyncClient.send = send_async  # type: ignore[method-assign]
    httpx.Client.send = send_sync  # type: ignore[method-assign]

    def desfazer() -> None:
        httpx.AsyncClient.send = envio_async  # type: ignore[method-assign]
        httpx.Client.send = envio_sync  # type: ignore[method-assign]

    return desfazer
