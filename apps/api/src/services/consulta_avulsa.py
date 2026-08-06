"""Consulta-avulsa (on-demand, cache-first).

Regra: toda leitura passa pelo cache. Só busca ao vivo em cache miss/stale.
Antes de retornar, garante `municipios_interesse(modo='avulso')` para o usuário
— senão o RLS esconderia do próprio usuário o resultado que ele acabou de buscar.

Bookkeeping de `sync_runs` roda em sessão AUTÔNOMA: o request inteiro é uma
transação e um erro daria rollback, perdendo o registro do incidente. sync_runs
não tem RLS, então pode ser gravado por fora com commit próprio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.base import get_connector
from ..core.config import settings
from ..db.session import SessionLocal
from ..ingestion.merge import merge_record
from ..jobs import curadoria as curadoria_job
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.proposta import Proposta
from ..models.sync_run import SyncRun
from . import fontes as fontes_service
from . import propostas as propostas_service


async def _garantir_municipio_avulso(
    session: AsyncSession, usuario_id: uuid.UUID, ibge: str
) -> None:
    """Registra o município como 'avulso' para o usuário (idempotente)."""
    stmt = (
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    await session.execute(stmt)


async def _cache_fresco(session: AsyncSession, ibge: str, fonte: str) -> list[Proposta]:
    limite = datetime.now(UTC) - timedelta(seconds=settings.cache_ttl_seconds)
    stmt = select(Proposta).where(
        Proposta.municipio_ibge == ibge,
        Proposta.fonte == fonte,
        Proposta.cache_atualizado_em >= limite,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _registrar_sync(**kwargs) -> None:
    """Grava um SyncRun em transação própria (sobrevive a rollback do request)."""
    async with SessionLocal() as s:
        async with s.begin():
            s.add(SyncRun(**kwargs))


def _since() -> date:
    return date(date.today().year, 1, 1)


async def consulta_avulsa(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio_ibge: str,
    fonte: str,
) -> list[Proposta]:
    # 0) o usuário precisa "ver" este município para o RLS devolver o resultado
    await _garantir_municipio_avulso(session, usuario_id, municipio_ibge)
    session.add(
        AuditLog(
            usuario_id=usuario_id,
            acao="consulta_avulsa",
            entidade=f"{fonte}:{municipio_ibge}",
        )
    )

    # 1) cache fresco? devolve na hora (nunca chama a fonte)
    frescas = await _cache_fresco(session, municipio_ibge, fonte)
    if frescas:
        return frescas

    # 2) miss/stale → fetch ao vivo
    iniciado = datetime.now(UTC)
    try:
        connector = get_connector(fonte)
        registros = await connector.collect(municipio_ibge, since=_since())
        n = 0
        for record in registros:
            # aglutina API + scraping quando o connector trouxe os dois lados
            canonica = merge_record(record)
            await propostas_service.upsert(session, canonica)
            n += 1
        # pílulas de categoria do que acabou de entrar: determinístico, sem rede
        # (o resumo por IA é outro pass, fora do request — jobs/curadoria).
        await curadoria_job.classificar_pendentes(session)
    except Exception as exc:  # nunca engolir: registra incidente e propaga
        await _registrar_sync(
            usuario_id=usuario_id,
            fonte=fonte,
            tipo="avulso",
            status="erro",
            registros=0,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise

    await _registrar_sync(
        usuario_id=usuario_id,
        fonte=fonte,
        tipo="avulso",
        status="ok",
        registros=n,
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
    )

    # 3) devolve do cache (agora povoado), já sob o filtro de RLS
    return await propostas_service.listar(session, municipio=municipio_ibge, fonte=fonte)


# ── Busca em TEMPO REAL (multi-fonte) ───────────────────────────────────────
# A Captação filtra e a busca roda ao vivo: para cada município do perfil (ou o
# município filtrado) × fonte de captação relevante, reusa o fluxo cache-first
# acima (cache fresco responde na hora; stale/miss vai à fonte — API e/ou
# scraping via connector). Cada fonte é best-effort: falha vira status (e
# sync_run), nunca derruba a busca inteira.

# fontes cujo connector produz PROPOSTAS (captação). O recorte da v1 vive em
# `services/fontes.py` — hoje é a família TransfereGov (as APIs PostgREST, o CSV
# das discricionárias e o painel da Visão Geral).
CAPTACAO_FONTES: tuple[str, ...] = fontes_service.CAPTACAO


def _fontes_alvo(fonte: str | None, area: str | None, fontes_perfil: list[str] | None) -> list[str]:
    if fonte:
        return [fonte]
    if area:
        from .perfil import AREA_FONTES

        da_area = AREA_FONTES.get(area, set()) & set(CAPTACAO_FONTES)
        if da_area:
            return sorted(da_area)
    if fontes_perfil:
        do_perfil = set(fontes_perfil) & set(CAPTACAO_FONTES)
        if do_perfil:
            return sorted(do_perfil)
    return list(CAPTACAO_FONTES)


async def live_search(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio: str | None = None,
    fonte: str | None = None,
    area: str | None = None,
    **filtros,
):
    """Coleta ao vivo nas fontes e devolve (página, total do recorte, status).

    A coleta é a parte cara (uma das fontes baixa um CSV de ~1 GB) — daí ela ser
    ação explícita no painel. A leitura sai paginada como a da listagem: quem
    acabou de atualizar quer ver a primeira página, não as milhares de linhas.
    """
    from ..models.preferencias import PreferenciasUsuario

    if municipio:
        ibges = [municipio]
    else:
        ibges = list(
            (
                await session.execute(
                    select(MunicipioInteresse.ibge).where(
                        MunicipioInteresse.usuario_id == usuario_id
                    )
                )
            )
            .scalars()
            .all()
        )
    pref = (
        await session.execute(
            select(PreferenciasUsuario).where(PreferenciasUsuario.usuario_id == usuario_id)
        )
    ).scalar_one_or_none()
    fontes = _fontes_alvo(fonte, area, list(pref.fontes or []) if pref else None)

    status_fontes: list[dict] = []
    for ibge in ibges:
        for f in fontes:
            try:
                await consulta_avulsa(session, usuario_id=usuario_id, municipio_ibge=ibge, fonte=f)
                status_fontes.append({"fonte": f, "municipio_ibge": ibge, "status": "ok"})
            except Exception as exc:  # registrado em sync_runs pela consulta_avulsa
                status_fontes.append(
                    {
                        "fonte": f,
                        "municipio_ibge": ibge,
                        "status": "erro",
                        "erro": type(exc).__name__,
                    }
                )

    rows, total = await propostas_service.listar_pagina(
        session, municipio=municipio, fonte=fonte, area=area, **filtros
    )
    return rows, total, status_fontes
