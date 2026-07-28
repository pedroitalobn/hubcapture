"""Diagnóstico de fontes (admin) — responde "as APIs estão funcionais?".

`GET /admin/fontes` roda o `health_check()` de TODOS os connectors ao vivo (em
paralelo, com timeout individual) e junta a última execução de coleta por fonte
(`sync_runs`) + o estado dos providers de scraping/IA. É o raio-X da ingestão
em produção: o admin vê na hora qual fonte responde, qual falha e o que falta
configurar (ex.: chave do Firecrawl ou do Portal da Transparência).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors.base import available_sources, get_connector
from ...core.users import current_superuser
from ...models.sync_run import SyncRun
from ...models.usuario import Usuario
from ...schemas.config import DiagnosticoFontes, FonteDiagnostico, UltimaColeta
from ...services import config as config_service
from ..deps import get_platform_db

router = APIRouter(tags=["admin"])

HEALTH_TIMEOUT = 10.0  # s por fonte — fonte pendurada não trava o diagnóstico


async def _health(fonte: str) -> bool:
    try:
        return await asyncio.wait_for(
            get_connector(fonte).health_check(), timeout=HEALTH_TIMEOUT
        )
    except Exception:
        return False


@router.get("/admin/fontes", response_model=DiagnosticoFontes)
async def diagnostico_fontes(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> DiagnosticoFontes:
    fontes = available_sources()

    # última coleta por fonte (global — qualquer usuário/agendado)
    runs = (
        (
            await session.execute(
                select(SyncRun).order_by(SyncRun.iniciado_em.desc().nullslast()).limit(200)
            )
        )
        .scalars()
        .all()
    )
    ultima: dict[str, UltimaColeta] = {}
    for r in runs:
        if r.fonte and r.fonte not in ultima:
            ultima[r.fonte] = UltimaColeta(
                status=r.status,
                registros=r.registros,
                finalizado_em=r.finalizado_em.isoformat() if r.finalizado_em else None,
                erro=(r.erro or None) and r.erro[:300],
            )

    saude = await asyncio.gather(*(_health(f) for f in fontes))

    return DiagnosticoFontes(
        fontes=[
            FonteDiagnostico(fonte=f, saudavel=ok, ultima_coleta=ultima.get(f))
            for f, ok in zip(fontes, saude, strict=False)
        ],
        firecrawl_configurado=bool(await config_service.resolver("firecrawl_api_key")),
        crawl4ai_configurado=bool(await config_service.resolver("crawl4ai_base_url")),
        llm_configurado=bool(await config_service.resolver("llm_api_key")),
        emendas_api_key_configurada=bool(
            await config_service.resolver("emendas_api_key")
        ),
    )
