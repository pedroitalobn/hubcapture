"""Classificação de propostas por ano — critério é o ano de CRIAÇÃO.

Cenário do bug: proposta criada em 2022 que recebeu movimentação em 2026 não
pode ser listada/contada como 2026.
"""

from __future__ import annotations

from decimal import Decimal

from src.db.session import rls_session
from src.services import propostas as service


async def _cenario(seed_user, seed_municipio, seed_proposta, email: str):
    u = await seed_user(email)
    await seed_municipio(u, "3550308")
    # criada em 2022, mexida em 2026 (a que aparecia errada em 2026)
    await seed_proposta(
        "transferegov_ff", "P-2022", "3550308", "Antiga",
        ano=2022, data_atualizacao_fonte="2026-01-30", valor_total="100",
    )
    # criada em 2026, sem movimentação registrada
    await seed_proposta(
        "transferegov_ff", "P-2026", "3550308", "Nova",
        ano=2026, valor_total="50",
    )
    return u


async def test_filtro_por_ano_usa_criacao(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await _cenario(seed_user, seed_municipio, seed_proposta, "a1@a.com")
    async with rls_session(u) as s:
        de_2026 = await service.listar(s, ano=2026)
        de_2022 = await service.listar(s, ano=2022)

    # atualizada em 2026, mas criada em 2022 → só aparece em 2022
    assert [p.id_externo for p in de_2026] == ["P-2026"]
    assert [p.id_externo for p in de_2022] == ["P-2022"]


async def test_ordenacao_por_ano_de_criacao(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await _cenario(seed_user, seed_municipio, seed_proposta, "a2@a.com")
    async with rls_session(u) as s:
        rows = await service.listar(s)

    assert [p.ano for p in rows] == [2026, 2022]


async def test_agrupamento_por_ano(seed_user, seed_municipio, seed_proposta) -> None:
    u = await _cenario(seed_user, seed_municipio, seed_proposta, "a3@a.com")
    await seed_proposta(
        "transferegov_ff", "P-SEM-ANO", "3550308", "Sem ano", valor_total="10"
    )

    async with rls_session(u) as s:
        safras = await service.anos(s)

    # mais recente primeiro; safra sem ano informado vai para o fim
    assert [a.ano for a in safras] == [2026, 2022, None]
    assert [a.total for a in safras] == [1, 1, 1]
    assert [a.valor_total for a in safras] == [
        Decimal("50"),
        Decimal("100"),
        Decimal("10"),
    ]
