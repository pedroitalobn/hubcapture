"""RLS: isolamento por município entre tenants (rodando como a role de app)."""

from __future__ import annotations

from src.db.session import SessionLocal, rls_session
from src.services import propostas as svc


async def test_rls_isola_propostas_por_tenant(seed_user, seed_municipio, seed_proposta) -> None:
    a = await seed_user("a@a.com")
    b = await seed_user("b@b.com")
    await seed_municipio(a, "2301109")
    await seed_municipio(b, "3550308")
    await seed_proposta("transferegov_ff", "A1", "2301109")
    await seed_proposta("transferegov_ff", "B1", "3550308")

    async with rls_session(a) as s:
        rows = await svc.listar(s)
        assert {r.id_externo for r in rows} == {"A1"}  # A só vê o município dele

    async with rls_session(b) as s:
        rows = await svc.listar(s)
        assert {r.id_externo for r in rows} == {"B1"}  # B só vê o dele


async def test_sem_tenant_setado_nao_ve_nada(seed_user, seed_municipio, seed_proposta) -> None:
    a = await seed_user("a@a.com")
    await seed_municipio(a, "2301109")
    await seed_proposta("transferegov_ff", "A1", "2301109")

    # sessão da role de app SEM set_config → current_setting é NULL → policy nega
    async with SessionLocal() as s:
        async with s.begin():
            rows = await svc.listar(s)
    assert rows == []
