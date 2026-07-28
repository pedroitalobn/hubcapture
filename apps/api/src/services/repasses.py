"""Serviço de repasses (recebidos) — cache-first, upsert, visão geral e sync.

Espelha o padrão de `services/propostas.py`. Leitura sempre do cache (RLS isola
por município); o fetch ao vivo (sync) usa os connectors + normalize_repasse.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.base import get_connector
from ..ingestion.normalizer_repasse import normalize_repasse
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.repasse import Repasse
from ..schemas.repasse import (
    FonteResumo,
    RepasseCanonico,
    RepasseRead,
    RepassesPorDia,
    VisaoGeral,
)
from ._sync import registrar_sync

_UPSERT_FIELDS = (
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "data_repasse",
    "competencia",
    "descricao",
    "categoria",
    "orgao_superior",
    "natureza",
    "valor",
    "documento",
    "emenda",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


def _signed(valor: Decimal | None, natureza: str | None) -> Decimal:
    """Dedução entra negativa; crédito/repasse positivo (líquido do FPM)."""
    if valor is None:
        return Decimal(0)
    return -valor if natureza == "deducao" else valor


async def listar(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> list[Repasse]:
    stmt = select(Repasse)
    if municipio:
        stmt = stmt.where(Repasse.municipio_ibge == municipio)
    if fonte:
        stmt = stmt.where(Repasse.fonte == fonte)
    if inicio:
        stmt = stmt.where(Repasse.data_repasse >= inicio)
    if fim:
        stmt = stmt.where(Repasse.data_repasse <= fim)
    stmt = stmt.order_by(Repasse.data_repasse.desc().nullslast())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert(session: AsyncSession, canonico: RepasseCanonico) -> None:
    now = datetime.now(UTC)
    values = canonico.model_dump()
    values["cache_atualizado_em"] = now
    stmt = pg_insert(Repasse).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(constraint="uq_repasses_fonte_id_externo", set_=update_set)
    await session.execute(stmt)


async def visao_geral(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> VisaoGeral:
    """Painel consolidado: KPI de total pago, cards por fonte e feed por data."""
    rows = await listar(session, municipio=municipio, inicio=inicio, fim=fim)

    total = Decimal(0)
    por_fonte_total: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    por_fonte_qtd: dict[str, int] = defaultdict(int)
    por_dia: dict[date, list[Repasse]] = defaultdict(list)

    for r in rows:
        s = _signed(r.valor, r.natureza)
        total += s
        por_fonte_total[r.fonte] += s
        por_fonte_qtd[r.fonte] += 1
        if r.data_repasse is not None:
            por_dia[r.data_repasse].append(r)

    fontes = [
        FonteResumo(fonte=f, total=por_fonte_total[f], movimentacoes=por_fonte_qtd[f])
        for f in sorted(por_fonte_total, key=lambda x: por_fonte_total[x], reverse=True)
    ]
    feed = [
        RepassesPorDia(
            data=d,
            subtotal=sum((_signed(r.valor, r.natureza) for r in por_dia[d]), Decimal(0)),
            itens=[RepasseRead.model_validate(r) for r in por_dia[d]],
        )
        for d in sorted(por_dia, reverse=True)
    ]
    return VisaoGeral(
        total_pago=total,
        movimentacoes=len(rows),
        inicio=inicio,
        fim=fim,
        fontes=fontes,
        feed=feed,
    )


async def sync_municipio(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio_ibge: str,
    fontes: list[str],
) -> int:
    """Fetch ao vivo dos recebidos de um município para as fontes dadas.

    Garante `municipios_interesse` (senão o RLS esconde o resultado), grava
    audit_log e registra cada fonte em sync_runs. Retorna o total gravado.
    """
    stmt = (
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=municipio_ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    await session.execute(stmt)
    session.add(
        AuditLog(
            usuario_id=usuario_id,
            acao="sync_repasses",
            entidade=f"{','.join(fontes)}:{municipio_ibge}",
        )
    )

    total = 0
    for fonte in fontes:
        iniciado = datetime.now(UTC)
        try:
            connector = get_connector(fonte)
            registros = await connector.collect(municipio_ibge, since=_since())
            n = 0
            for record in registros:
                await upsert(session, normalize_repasse(record))
                n += 1
            total += n
        except Exception as exc:  # nunca engolir: registra incidente e propaga
            await registrar_sync(
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
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=fonte,
            tipo="avulso",
            status="ok",
            registros=n,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
        )
    return total


def _since() -> date:
    return date(date.today().year, 1, 1)
