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
from .core.latencia import LatenciaMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Segurança primeiro: em produção, segredo de token padrão aborta o boot
    # (falha alta e explícita é melhor que sessão forjável em silêncio).
    from .core.seguranca_boot import verificar_segredos

    verificar_segredos(settings)

    # Bootstrap do superadmin inicial (ADMIN_EMAIL/ADMIN_PASSWORD). Best-effort:
    # falha aqui (ex.: banco ainda subindo) não impede a API de servir.
    try:
        from .core.bootstrap import ensure_admin, ensure_planos

        await ensure_admin()
        await ensure_planos()  # 4 planos padrão (free/start/pro/business)
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

# Por último = camada mais externa: mede o request inteiro (CORS incluso) e
# carimba X-Response-Time; request lenta vira WARN no log (core/latencia.py).
app.add_middleware(LatenciaMiddleware)


@app.get("/health", tags=["infra"])
async def health() -> dict[str, str]:
    """Vivo? E, principalmente, QUAL versão está no ar.

    O commit vem carimbado na imagem em build (ARG GIT_SHA). Sem ele, um deploy
    que não atualizou é indistinguível de um que atualizou — foi exatamente o
    que aconteceu com a imagem parada num commit antigo. Agora dá para conferir
    de fora: `curl https://<dominio>/health`.
    """
    return {
        "status": "ok",
        "commit": settings.git_sha,
        "ref": settings.git_ref,
        "build": settings.build_time,
    }


def register_routers() -> None:
    """Inclui os routers da v1. Chamado no import; separado para facilitar testes."""
    from .api.v1 import (
        admin,
        admin_assessoria,
        admin_config,
        admin_fontes,
        admin_helpdesk,
        admin_modulos,
        alertas,
        assessoria,
        auth,
        conformidade,
        consulta_avulsa,
        conta,
        contatos,
        copiloto,
        favoritos,
        helpdesk,
        integracoes,
        monitoramentos,
        municipios,
        noticias,
        obras,
        onboarding,
        pareceres,
        pastas,
        perfil,
        planos,
        propostas,
        repasses,
        ui,
        webhooks,
    )

    for mod in (
        auth,
        perfil,
        municipios,
        propostas,
        pareceres,
        consulta_avulsa,
        repasses,
        conformidade,
        obras,
        onboarding,
        favoritos,
        pastas,
        conta,
        contatos,
        integracoes,
        monitoramentos,
        alertas,
        assessoria,
        noticias,
        helpdesk,
        planos,
        admin,
        admin_assessoria,
        admin_config,
        admin_fontes,
        admin_helpdesk,
        admin_modulos,
        copiloto,
        ui,
        webhooks,
    ):
        app.include_router(mod.router, prefix="/api/v1")


register_routers()
