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
from ..ingestion.merge import merge
from ..ingestion.normalizer import normalize
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.proposta import Proposta
from ..models.sync_run import SyncRun
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
            canonica = merge(normalize(record), None)
            await propostas_service.upsert(session, canonica)
            n += 1
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
    return await propostas_service.listar(
        session, municipios=[municipio_ibge], fonte=fonte
    )
