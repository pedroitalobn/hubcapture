"""Serviço de obras (execução) — cache-first, resumo e sync multi-fonte.

Espelha `services/conformidade.py`/`services/repasses.py`. Leitura sempre do
cache (RLS por município); o fetch ao vivo roda os connectors de obras
(sismob/simec/caixa) e faz upsert por `(fonte, id_externo)`.
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
from ..ingestion.normalizer_obra import normalize_obra
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.obra import Obra
from ..schemas.obra import ObraCanonica, ObraRead, ObrasResumo, SituacaoResumo
from ._sync import registrar_sync
from ._territorio import Municipios
from ._territorio import filtrar as filtrar_municipio

FONTES_PADRAO = ("sismob", "simec", "caixa")

_UPSERT_FIELDS = (
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "nome",
    "objeto",
    "programa",
    "eixo",
    "situacao",
    "percentual_execucao",
    "valor_investimento",
    "valor_repassado",
    "data_inicio",
    "data_fim_prevista",
    "latitude",
    "longitude",
    "endereco",
    "orgao",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


async def listar(
    session: AsyncSession,
    *,
    municipio: Municipios = None,
    fonte: str | None = None,
    situacao: str | None = None,
) -> list[Obra]:
    stmt = select(Obra)
    # um município, vários (recorte do painel) ou nenhum (todo o território)
    stmt = filtrar_municipio(stmt, Obra.municipio_ibge, municipio)
    if fonte:
        stmt = stmt.where(Obra.fonte == fonte)
    if situacao:
        stmt = stmt.where(Obra.situacao == situacao)
    stmt = stmt.order_by(Obra.municipio_ibge, Obra.fonte, Obra.nome.nullslast())
    return list((await session.execute(stmt)).scalars().all())


async def upsert(session: AsyncSession, canonica: ObraCanonica) -> None:
    now = datetime.now(UTC)
    values = canonica.model_dump()
    values["cache_atualizado_em"] = now
    stmt = pg_insert(Obra).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(constraint="uq_obras_fonte_id_externo", set_=update_set)
    await session.execute(stmt)


async def resumo(session: AsyncSession, *, municipio: Municipios = None) -> ObrasResumo:
    """KPIs de execução + quebra por situação + obras (com geo p/ o mapa)."""
    obras = await listar(session, municipio=municipio)

    por_situacao: dict[str, list[Obra]] = defaultdict(list)
    for o in obras:
        por_situacao[o.situacao or "—"].append(o)

    def _conta(sit: str) -> int:
        return len(por_situacao.get(sit, []))

    def _soma(campo: str) -> Decimal:
        return sum((getattr(o, campo) or Decimal(0) for o in obras), Decimal(0))

    situacoes = [
        SituacaoResumo(
            situacao=sit,
            total=len(itens),
            valor_investimento=sum((o.valor_investimento or Decimal(0) for o in itens), Decimal(0)),
        )
        for sit, itens in sorted(por_situacao.items())
    ]
    return ObrasResumo(
        total=len(obras),
        em_execucao=_conta("em_execucao"),
        concluidas=_conta("concluida"),
        paralisadas=_conta("paralisada"),
        valor_investimento_total=_soma("valor_investimento"),
        valor_repassado_total=_soma("valor_repassado"),
        por_situacao=situacoes,
        obras=[ObraRead.model_validate(o) for o in obras],
    )


async def sync_municipio(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio_ibge: str,
    fontes: list[str] | None = None,
) -> int:
    """Fetch ao vivo das obras nas fontes pedidas. Garante municipios_interesse.

    Cada fonte roda em best-effort: uma que falha registra `sync_runs.erro` e não
    derruba as demais (degradação graciosa, como o onboarding).
    """
    await session.execute(
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=municipio_ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    session.add(AuditLog(usuario_id=usuario_id, acao="sync_obras", entidade=municipio_ibge))

    total = 0
    for fonte in fontes or list(FONTES_PADRAO):
        iniciado = datetime.now(UTC)
        try:
            registros = await get_connector(fonte).collect(municipio_ibge, since=_since())
        except Exception as exc:
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
            continue
        n = 0
        for record in registros:
            await upsert(session, normalize_obra(record))
            n += 1
        total += n
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
    return date(date.today().year - 1, 1, 1)
