"""Primeiro sync do território — dispara após o onboarding, em background.

Cobre as 4 dimensões do ciclo com dados REAIS das fontes (API + scraping via
facade): captação (propostas), recebidos (repasses), conformidade fiscal e
obras. O onboarding responde na hora e o painel vai se povoando conforme cada
fonte conclui (cada etapa commita a sua própria sessão RLS).

IMPORTANTE: o agendamento usa `asyncio.create_task` — NÃO BackgroundTasks do
FastAPI. O Starlette roda BackgroundTasks dentro do envio da resposta, ANTES do
teardown da dependência de sessão: o sync rodaria com a transação do onboarding
ainda aberta, colidiria com as linhas não commitadas (lock em
municipios_interesse/usuarios) e seguraria o commit do perfil até a última fonte
responder. Com create_task o request commita imediatamente e o sync corre solto.

Best-effort por fonte: uma fonte fora do ar registra o incidente em `sync_runs`
(feito pelos serviços chamados) e NÃO derruba as demais — o usuário sempre chega
num painel com o que as fontes saudáveis entregaram.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from ..db.session import rls_session
from ..jobs import curadoria as curadoria_job
from . import conformidade as conformidade_service
from . import consulta_avulsa as consulta_service
from . import fontes as fontes_service
from . import obras as obras_service
from . import repasses as repasses_service

log = logging.getLogger("hubcapture.primeiro_sync")

# Fontes de captação (propostas) e de recebidos (repasses) que o 1º sync cobre —
# ambas saem do recorte de fontes habilitadas (`services/fontes.py`).
FONTES_CAPTACAO = fontes_service.CAPTACAO
FONTES_RECEBIDOS = fontes_service.RECEBIDOS
# Obras por área de interesse; sem área conhecida, tenta as três.
AREA_FONTES_OBRAS: dict[str, str] = {
    "saude": "sismob",
    "educacao": "simec",
    "infraestrutura": "caixa",
}


def _fontes_captacao(fontes: list[str]) -> list[str]:
    escolhidas = [f for f in FONTES_CAPTACAO if f in fontes]
    return escolhidas or list(FONTES_CAPTACAO)


def _fontes_recebidos(fontes: list[str]) -> list[str]:
    escolhidas = [f for f in FONTES_RECEBIDOS if f in fontes]
    return escolhidas or list(FONTES_RECEBIDOS)


def _fontes_obras(areas: list[str]) -> list[str]:
    escolhidas = sorted({AREA_FONTES_OBRAS[a] for a in areas if a in AREA_FONTES_OBRAS})
    return escolhidas or sorted(set(AREA_FONTES_OBRAS.values()))


# Referências fortes das tasks em voo (senão o GC pode cancelá-las no meio).
_tasks: set[asyncio.Task] = set()


def agendar(
    usuario_id: uuid.UUID,
    municipios: list[str],
    fontes: list[str],
    areas: list[str],
) -> None:
    """Dispara o 1º sync fora do ciclo do request (ver docstring do módulo)."""
    task = asyncio.create_task(executar(usuario_id, municipios, fontes, areas))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def executar(
    usuario_id: uuid.UUID,
    municipios: list[str],
    fontes: list[str],
    areas: list[str],
) -> None:
    """Sincroniza todas as dimensões para cada município do perfil."""
    for ibge in municipios:
        # 1) Captação — consulta-avulsa é cache-first e registra sync_runs.
        for fonte in _fontes_captacao(fontes):
            try:
                async with rls_session(usuario_id) as s:
                    await consulta_service.consulta_avulsa(
                        s, usuario_id=usuario_id, municipio_ibge=ibge, fonte=fonte
                    )
            except Exception:
                log.warning("1º sync captação falhou: %s/%s", fonte, ibge, exc_info=True)

        # 1b) Curadoria por IA (resumo + pílulas refinadas) do que acabou de
        # entrar. Fora do request de propósito: é a única etapa que chama LLM.
        try:
            async with rls_session(usuario_id) as s:
                await curadoria_job.curar_com_ia(s)
        except Exception:
            log.warning("1º sync curadoria falhou: %s", ibge, exc_info=True)

        # 2) Recebidos — uma fonte por sessão para isolar falhas.
        for fonte in _fontes_recebidos(fontes):
            try:
                async with rls_session(usuario_id) as s:
                    await repasses_service.sync_municipio(
                        s, usuario_id=usuario_id, municipio_ibge=ibge, fontes=[fonte]
                    )
            except Exception:
                log.warning("1º sync recebidos falhou: %s/%s", fonte, ibge, exc_info=True)

        # 3) Conformidade fiscal (CAUC/CAPAG).
        try:
            async with rls_session(usuario_id) as s:
                await conformidade_service.sync_municipio(
                    s, usuario_id=usuario_id, municipio_ibge=ibge
                )
        except Exception:
            log.warning("1º sync conformidade falhou: %s", ibge, exc_info=True)

        # 4) Obras (execução) — o serviço já é best-effort por fonte.
        try:
            async with rls_session(usuario_id) as s:
                await obras_service.sync_municipio(
                    s,
                    usuario_id=usuario_id,
                    municipio_ibge=ibge,
                    fontes=_fontes_obras(areas),
                )
        except Exception:
            log.warning("1º sync obras falhou: %s", ibge, exc_info=True)
