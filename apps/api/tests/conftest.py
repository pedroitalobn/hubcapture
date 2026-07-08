"""Fixtures de teste.

Os testes usam o Postgres local (mesmo do docker-compose). Seeds/limpeza rodam
como OWNER (migrator); as asserções de RLS rodam como a role de app via
`rls_session`, para que o teste seja válido (owner/superuser burlaria o RLS).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.db.session import engine as _app_engine

# pytest-asyncio cria um event loop por teste; conexões asyncpg são presas ao
# loop. NullPool evita reuso de conexão entre loops no engine de owner, e o
# teardown descarta o pool do engine da app para o próximo teste recriar no
# seu próprio loop.
_owner_engine = create_async_engine(settings.database_migrator_url, poolclass=NullPool)

_TABLES = (
    "alertas, monitoramentos, favoritos, pasta_propostas, pastas, audit_log, "
    "sync_runs, proposta_embeddings, propostas, municipios_interesse, "
    "preferencias_usuario, usuarios"
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db() -> AsyncIterator[None]:
    async with _owner_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    yield
    # descarta pools presos ao loop deste teste
    await _app_engine.dispose()
    await _owner_engine.dispose()


@pytest_asyncio.fixture
async def seed_user() -> Callable[..., Awaitable[uuid.UUID]]:
    async def _seed(email: str, papel: str = "executivo") -> uuid.UUID:
        uid = uuid.uuid4()
        async with _owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO usuarios (id, senha_hash, email, is_active, "
                    "is_superuser, is_verified, papel, optin_wpp) "
                    "VALUES (:id,'x',:email,true,false,false,:papel,false)"
                ),
                {"id": uid, "email": email, "papel": papel},
            )
        return uid

    return _seed


@pytest_asyncio.fixture
async def seed_municipio() -> Callable[..., Awaitable[None]]:
    async def _seed(usuario_id: uuid.UUID, ibge: str, modo: str = "monitorado") -> None:
        async with _owner_engine.begin() as conn:
            # municipios_interesse tem FORCE RLS → até o owner precisa do tenant
            # setado para satisfazer o WITH CHECK (usuario_id = current_setting).
            await conn.execute(
                text("SELECT set_config('app.usuario_id', :uid, true)"),
                {"uid": str(usuario_id)},
            )
            await conn.execute(
                text(
                    "INSERT INTO municipios_interesse (usuario_id, ibge, modo) "
                    "VALUES (:uid,:ibge,:modo) ON CONFLICT DO NOTHING"
                ),
                {"uid": usuario_id, "ibge": ibge, "modo": modo},
            )

    return _seed


@pytest_asyncio.fixture
async def seed_proposta() -> Callable[..., Awaitable[None]]:
    async def _seed(fonte: str, id_externo: str, ibge: str, titulo: str = "P") -> None:
        async with _owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                    "cache_atualizado_em) VALUES (:f,:e,:t,:ibge, now())"
                ),
                {"f": fonte, "e": id_externo, "t": titulo, "ibge": ibge},
            )

    return _seed
