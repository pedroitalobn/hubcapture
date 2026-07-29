"""Serviço de conformidade fiscal (CAUC/CAPAG) — cache-first, resumo e sync.

Espelha `services/repasses.py`. Leitura sempre do cache (RLS por município);
o fetch ao vivo usa o connector `siconfi` + normalize_conformidade.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.base import get_connector
from ..ingestion.normalizer_conformidade import normalize_conformidade
from ..models.audit_log import AuditLog
from ..models.conformidade import Conformidade
from ..models.municipio_interesse import MunicipioInteresse
from ..schemas.conformidade import (
    ConformidadeCanonica,
    ConformidadeRead,
    ConformidadeResumo,
    SecaoResumo,
)
from ._sync import registrar_sync

_UPSERT_FIELDS = (
    "municipio_nome",
    "uf",
    "secao",
    "descricao",
    "status",
    "validade",
    "orgao",
    "valor",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


async def listar(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    tipo: str | None = None,
) -> list[Conformidade]:
    stmt = select(Conformidade)
    if municipio:
        stmt = stmt.where(Conformidade.municipio_ibge == municipio)
    if tipo:
        stmt = stmt.where(Conformidade.tipo == tipo)
    stmt = stmt.order_by(Conformidade.secao.nullslast(), Conformidade.numero)
    return list((await session.execute(stmt)).scalars().all())


async def upsert(session: AsyncSession, canonica: ConformidadeCanonica) -> None:
    now = datetime.now(UTC)
    values = canonica.model_dump()
    values["cache_atualizado_em"] = now
    stmt = pg_insert(Conformidade).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(
        constraint="uq_conformidades_muni_tipo_numero", set_=update_set
    )
    await session.execute(stmt)


async def resumo(session: AsyncSession, *, municipio: str | None = None) -> ConformidadeResumo:
    """KPIs do CAUC (por status/seção) + rating CAPAG."""
    rows = await listar(session, municipio=municipio)
    cauc = [r for r in rows if r.tipo == "cauc"]
    capag = next((r for r in rows if r.tipo == "capag"), None)

    por_secao: dict[str, list[Conformidade]] = defaultdict(list)
    for r in cauc:
        por_secao[r.secao or "—"].append(r)

    def _conta(itens: list[Conformidade], status: str) -> int:
        return sum(1 for i in itens if i.status == status)

    secoes = [
        SecaoResumo(
            secao=secao,
            total=len(por_secao[secao]),
            comprovados=_conta(por_secao[secao], "comprovado"),
            a_comprovar=_conta(por_secao[secao], "a_comprovar"),
            desativados=_conta(por_secao[secao], "desativado"),
        )
        for secao in sorted(por_secao)
    ]
    return ConformidadeResumo(
        total=len(cauc),
        comprovados=_conta(cauc, "comprovado"),
        a_comprovar=_conta(cauc, "a_comprovar"),
        desativados=_conta(cauc, "desativado"),
        secoes=secoes,
        capag=ConformidadeRead.model_validate(capag) if capag else None,
        requisitos=[ConformidadeRead.model_validate(r) for r in cauc],
    )


async def sync_municipio(
    session: AsyncSession, *, usuario_id: uuid.UUID, municipio_ibge: str
) -> int:
    """Fetch ao vivo da conformidade (CAUC/CAPAG). Garante municipios_interesse."""
    await session.execute(
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=municipio_ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    session.add(AuditLog(usuario_id=usuario_id, acao="sync_conformidade", entidade=municipio_ibge))
    iniciado = datetime.now(UTC)
    try:
        registros = await get_connector("siconfi").collect(municipio_ibge, since=_since())
        n = 0
        for record in registros:
            await upsert(session, normalize_conformidade(record))
            n += 1
    except Exception as exc:
        await registrar_sync(
            usuario_id=usuario_id,
            fonte="siconfi",
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
        fonte="siconfi",
        tipo="avulso",
        status="ok",
        registros=n,
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
    )
    return n


def _since() -> date:
    return date(date.today().year, 1, 1)
