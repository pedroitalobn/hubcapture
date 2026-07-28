"""Endpoints de captação sobre a app real (roteamento + contrato).

`/proposals/summary` é um caminho literal convivendo com
`/proposals/{proposta_id}`: declarado na ordem errada, o FastAPI tenta ler
'summary' como UUID e o painel quebra com 422. Estes testes prendem a ordem.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from src.core.users import current_active_user
from src.db.session import SessionLocal
from src.main import app
from src.models.usuario import Usuario
from tests.conftest import _owner_engine

IBGE = "3106200"


@pytest_asyncio.fixture
async def client(seed_user, seed_municipio) -> AsyncIterator[AsyncClient]:
    uid = await seed_user("api@x.com")
    await seed_municipio(uid, IBGE)

    async with SessionLocal() as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()

    app.dependency_overrides[current_active_user] = lambda: usuario
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def seed_proposta_ano():
    async def _seed(id_externo: str, *, ano: int | None, valor: str | None, titulo: str) -> None:
        async with _owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                    "ano, valor_total, cache_atualizado_em) "
                    "VALUES ('transferegov_ff',:e,:t,:ibge,:ano,:valor, now())"
                ),
                {"e": id_externo, "t": titulo, "ibge": IBGE, "ano": ano, "valor": valor},
            )

    return _seed


async def test_summary_nao_e_lido_como_uuid(client, seed_proposta_ano) -> None:
    await seed_proposta_ano("A", ano=2026, valor="100", titulo="2026-a")

    resp = await client.get("/api/v1/proposals/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["por_ano"] == [{"ano": 2026, "total": 1, "valor_total": "100.00"}]


async def test_summary_filtra_por_ano(client, seed_proposta_ano) -> None:
    await seed_proposta_ano("A", ano=2026, valor="100", titulo="a")
    await seed_proposta_ano("B", ano=2025, valor="30", titulo="b")

    resp = await client.get("/api/v1/proposals/summary", params={"ano": 2025})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ano"] == 2025
    assert body["total"] == 1
    assert body["valor_total"] == "30.00"
    # a lista de anos continua completa — é ela que alimenta o filtro
    assert [a["ano"] for a in body["por_ano"]] == [2026, 2025]


async def test_listar_aceita_filtro_de_ano(client, seed_proposta_ano) -> None:
    await seed_proposta_ano("A", ano=2026, valor=None, titulo="a")
    await seed_proposta_ano("B", ano=2025, valor=None, titulo="b")

    resp = await client.get("/api/v1/proposals", params={"ano": 2026})
    assert resp.status_code == 200
    assert [p["titulo"] for p in resp.json()] == ["a"]


async def test_proposta_por_id_continua_funcionando(client, seed_proposta_ano) -> None:
    await seed_proposta_ano("A", ano=2026, valor=None, titulo="a")
    lista = (await client.get("/api/v1/proposals")).json()

    resp = await client.get(f"/api/v1/proposals/{lista[0]['id']}")
    assert resp.status_code == 200
    assert resp.json()["titulo"] == "a"


async def test_deadlines_continua_funcionando(client) -> None:
    """A outra rota literal do router não pode ter sido quebrada pela nova."""
    resp = await client.get("/api/v1/proposals/deadlines")
    assert resp.status_code == 200
    assert resp.json() == []
