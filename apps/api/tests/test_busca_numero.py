"""Busca de propostas pelo número (NR_PROPOSTA), sob RLS."""

from __future__ import annotations

from src.db.session import rls_session
from src.services import propostas as svc


async def test_busca_por_numero_filtra_e_casa_parcial(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await seed_user("num@num.com")
    await seed_municipio(uid, "2304400")
    await seed_proposta("transferegov_disc", "P1", "2304400", numero_proposta="043210/2025")
    await seed_proposta("transferegov_disc", "P2", "2304400", numero_proposta="998877/2024")

    async with rls_session(uid) as s:
        exata = await svc.listar(s, numero="043210/2025")
        parcial = await svc.listar(s, numero="43210")
        vazia = await svc.listar(s, numero="000000")
        todas = await svc.listar(s, numero="   ")

    assert {r.id_externo for r in exata} == {"P1"}
    assert {r.id_externo for r in parcial} == {"P1"}  # busca parcial
    assert vazia == []
    assert {r.id_externo for r in todas} == {"P1", "P2"}  # termo vazio não filtra


async def test_busca_por_numero_casa_id_externo(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Fonte sem NR_PROPOSTA próprio: o número procurado é o id externo."""
    uid = await seed_user("ext@ext.com")
    await seed_municipio(uid, "2304400")
    await seed_proposta("fns", "SEM-NUMERO-777", "2304400")

    async with rls_session(uid) as s:
        rows = await svc.listar(s, numero="777")

    assert {r.id_externo for r in rows} == {"SEM-NUMERO-777"}


async def test_busca_por_numero_respeita_rls(
    seed_user, seed_municipio, seed_proposta
) -> None:
    dono = await seed_user("dono@x.com")
    outro = await seed_user("outro@x.com")
    await seed_municipio(dono, "2304400")
    await seed_municipio(outro, "3550308")
    await seed_proposta("transferegov_disc", "P1", "2304400", numero_proposta="043210/2025")

    async with rls_session(outro) as s:
        rows = await svc.listar(s, numero="043210/2025")

    assert rows == []  # número certo, território errado → nada
