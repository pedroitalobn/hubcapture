"""Medição de latência por request — o "está lento" vira dado.

Todo response sai com `X-Response-Time` (tempo até o primeiro byte). Request
acima de `log_request_lenta_ms` gera um WARN com método, rota, status, duração
e o estado do pool de conexões — as três causas clássicas de lentidão global
(event loop preso, pool esgotado, rota pesada) ficam distinguíveis no log de
produção (`docker logs <api>`) sem precisar reproduzir nada.

ASGI puro de propósito (não BaseHTTPMiddleware): não embrulha o corpo, então
não interfere no streaming dos endpoints SSE do copiloto. Para SSE o que se
mede é o tempo até o primeiro byte — a duração do stream não é lentidão.
"""

from __future__ import annotations

import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

log = logging.getLogger("hubcapture.latencia")


def _estado_do_pool() -> str:
    # import tardio: o engine puxa Settings/banco — o middleware não deve
    # impedir o import do app se o módulo de sessão mudar
    try:
        from ..db.session import engine

        return engine.sync_engine.pool.status()
    except Exception:  # noqa: BLE001 — diagnóstico nunca derruba o request
        return "pool ?"


class LatenciaMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        inicio = time.perf_counter()

        async def send_medido(message: Message) -> None:
            if message["type"] == "http.response.start":
                dur_ms = (time.perf_counter() - inicio) * 1000
                MutableHeaders(scope=message).append("X-Response-Time", f"{dur_ms:.0f}ms")
                if dur_ms >= settings.log_request_lenta_ms:
                    log.warning(
                        "request lenta: %s %s -> %s em %.0fms (%s)",
                        scope.get("method"),
                        scope.get("path"),
                        message.get("status"),
                        dur_ms,
                        _estado_do_pool(),
                    )
            await send(message)

        await self.app(scope, receive, send_medido)
