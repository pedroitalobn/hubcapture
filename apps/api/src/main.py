"""Bootstrap da API v1 (FastAPI). Monta /api/v1, CORS e OpenAPI.

Os routers de auth/propostas/consulta-avulsa são adicionados nos blocos seguintes.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Bootstrap do superadmin inicial (ADMIN_EMAIL/ADMIN_PASSWORD). Best-effort:
    # falha aqui (ex.: banco ainda subindo) não impede a API de servir.
    try:
        from .core.bootstrap import ensure_admin

        await ensure_admin()
    except Exception:  # noqa: BLE001
        logging.getLogger("hubcapture").warning("bootstrap do admin falhou", exc_info=True)
    yield


app = FastAPI(
    title="Hub Capture API",
    version="0.0.0",
    description="API pública v1 — propostas/repasses do governo (cache-first, RLS por usuário).",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)


@app.get("/health", tags=["infra"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def register_routers() -> None:
    """Inclui os routers da v1. Chamado no import; separado para facilitar testes."""
    from .api.v1 import (
        admin,
        admin_config,
        alertas,
        auth,
        conformidade,
        consulta_avulsa,
        copiloto,
        favoritos,
        monitoramentos,
        municipios,
        noticias,
        obras,
        onboarding,
        pastas,
        perfil,
        planos,
        propostas,
        repasses,
        webhooks,
    )

    for mod in (
        auth,
        perfil,
        municipios,
        propostas,
        consulta_avulsa,
        repasses,
        conformidade,
        obras,
        onboarding,
        favoritos,
        pastas,
        monitoramentos,
        alertas,
        noticias,
        planos,
        admin,
        admin_config,
        copiloto,
        webhooks,
    ):
        app.include_router(mod.router, prefix="/api/v1")


register_routers()
