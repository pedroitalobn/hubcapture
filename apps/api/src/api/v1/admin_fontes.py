"""Diagnóstico de fontes (admin) — responde "as APIs estão funcionais?".

`GET /admin/sources` roda o `health_check()` de TODOS os connectors ao vivo (em
paralelo, com timeout individual) e junta a última execução de coleta por fonte
(`sync_runs`) + o estado dos providers de scraping/IA. É o raio-X da ingestão
em produção: o admin vê na hora qual fonte responde, qual falha e o que falta
configurar (ex.: chave do Firecrawl ou do Portal da Transparência).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors import transferegov_disc
from ...connectors.base import available_sources, get_connector
from ...core.users import current_superuser
from ...models.proposta import Proposta
from ...models.sync_run import SyncRun
from ...models.usuario import Usuario
from ...schemas.config import DiagnosticoFontes, FonteDiagnostico, UltimaColeta
from ...services import config as config_service
from ...services import consulta_avulsa, llm_providers
from ..deps import get_platform_db

router = APIRouter(tags=["admin"])

HEALTH_TIMEOUT = 10.0  # s por fonte — fonte pendurada não trava o diagnóstico


class ResultadoLimpeza(BaseModel):
    removidas: int


@router.delete("/admin/proposals", response_model=ResultadoLimpeza)
async def zerar_propostas(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> ResultadoLimpeza:
    """Zera TODAS as propostas do sistema (uso: validação — recomeçar a coleta do
    zero). As FKs são ON DELETE CASCADE, então favoritos, pastas, monitoramentos,
    alertas e embeddings ligados às propostas somem junto. Só superuser."""
    # A contagem sai do rowcount do próprio DELETE: esta sessão não tem tenant e,
    # sob o FORCE RLS de propostas, um SELECT enxerga 0 linhas — o painel leria
    # "0 removidas" e a zeragem pareceria falhar mesmo apagando tudo.
    result = await session.execute(delete(Proposta))
    await session.commit()
    # Recomeçar a coleta do zero inclui a memória de coleta em processo: sem
    # isto a busca ao vivo pularia as fontes por até 6h (tentativa "fresca") e o
    # CSV nacional das discricionárias seria reaproveitado do cache.
    consulta_avulsa.limpar_cache_coleta()
    transferegov_disc.limpar_cache()
    return ResultadoLimpeza(removidas=int(result.rowcount or 0))


async def _health(fonte: str) -> bool:
    try:
        return await asyncio.wait_for(get_connector(fonte).health_check(), timeout=HEALTH_TIMEOUT)
    except Exception:
        return False


@router.get("/admin/sources", response_model=DiagnosticoFontes)
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
        llm_configurado=await llm_providers.configurado(),
        emendas_api_key_configurada=bool(await config_service.resolver("emendas_api_key")),
    )
