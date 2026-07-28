"""Captação por exercício: o painel abre no ano corrente e filtra os demais.

Antes o exercício só existia dentro de `execucao` (jsonb), que só o painel
SERPRO preenche — as demais fontes ficavam sem ano nenhum e o filtro do painel
vinha vazio.
"""

from __future__ import annotations

from decimal import Decimal

import pytest_asyncio
from sqlalchemy import text

from src.db.session import rls_session
from src.services import propostas as service
from tests.conftest import _owner_engine

IBGE = "3106200"


@pytest_asyncio.fixture
def seed_proposta_ano():
    async def _seed(
        id_externo: str,
        *,
        ano: int | None,
        valor: str | None = None,
        titulo: str = "P",
        ibge: str = IBGE,
    ) -> None:
        async with _owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                    "ano, valor_total, cache_atualizado_em) "
                    "VALUES ('transferegov_ff',:e,:t,:ibge,:ano,:valor, now())"
                ),
                {"e": id_externo, "t": titulo, "ibge": ibge, "ano": ano, "valor": valor},
            )

    return _seed


async def _tres_anos(seed) -> None:
    await seed("A", ano=2026, valor="100", titulo="2026-a")
    await seed("B", ano=2026, valor="200", titulo="2026-b")
    await seed("C", ano=2025, valor="50", titulo="2025-a")
    await seed("D", ano=None, valor="7", titulo="sem-ano")


async def test_listar_filtra_por_ano(seed_user, seed_municipio, seed_proposta_ano) -> None:
    uid = await seed_user("ano@x.com")
    await seed_municipio(uid, IBGE)
    await _tres_anos(seed_proposta_ano)

    async with rls_session(uid) as s:
        assert len(await service.listar(s)) == 4  # sem filtro = todos
        assert len(await service.listar(s, ano=2026)) == 2
        assert len(await service.listar(s, ano=2025)) == 1
        assert await service.listar(s, ano=1999) == []


async def test_resumo_soma_o_ano_em_foco(seed_user, seed_municipio, seed_proposta_ano) -> None:
    uid = await seed_user("resumo@x.com")
    await seed_municipio(uid, IBGE)
    await _tres_anos(seed_proposta_ano)

    async with rls_session(uid) as s:
        r = await service.resumo(s, ano=2026)

    assert r.ano == 2026
    assert r.total == 2
    assert r.valor_total == Decimal("300")
    assert r.municipios == 1
    assert {p.titulo for p in r.propostas} == {"2026-a", "2026-b"}


async def test_resumo_oferece_todos_os_anos_mesmo_filtrado(
    seed_user, seed_municipio, seed_proposta_ano
) -> None:
    """`por_ano` ignora o recorte: é ele que alimenta o próprio filtro de anos."""
    uid = await seed_user("anos@x.com")
    await seed_municipio(uid, IBGE)
    await _tres_anos(seed_proposta_ano)

    async with rls_session(uid) as s:
        r = await service.resumo(s, ano=2026)

    # mais recentes primeiro; as sem exercício no fim
    assert [a.ano for a in r.por_ano] == [2026, 2025, None]
    assert [a.total for a in r.por_ano] == [2, 1, 1]
    assert r.por_ano[0].valor_total == Decimal("300")


async def test_resumo_sem_filtro_conta_tudo(seed_user, seed_municipio, seed_proposta_ano) -> None:
    uid = await seed_user("todos@x.com")
    await seed_municipio(uid, IBGE)
    await _tres_anos(seed_proposta_ano)

    async with rls_session(uid) as s:
        r = await service.resumo(s)

    assert r.ano is None
    assert r.total == 4
    assert r.valor_total == Decimal("357")


async def test_resumo_respeita_o_rls(seed_user, seed_municipio, seed_proposta_ano) -> None:
    """Quem não acompanha o município não soma nada dele."""
    dono = await seed_user("dono@x.com")
    outro = await seed_user("outro@x.com")
    await seed_municipio(dono, IBGE)
    await _tres_anos(seed_proposta_ano)

    async with rls_session(outro) as s:
        r = await service.resumo(s)
    assert r.total == 0 and r.por_ano == []
