"""Repasses (recebidos): normalização/hash, RLS, agregação da visão geral e sync."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.connectors import base as cbase
from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion.normalizer_repasse import normalize_repasse
from src.services import repasses as service


def _record(valor: str = "1000.50", natureza: str = "credito") -> RawRecord:
    return RawRecord(
        source_id="fpm",
        id_externo=f"X:{natureza}",
        municipio_ibge="3550308",
        raw={
            "data_repasse": "2026-06-10",
            "descricao": "IPI",
            "categoria": "FPM",
            "orgao_superior": "Tesouro Nacional",
            "natureza": natureza,
            "valor": valor,
        },
    )


def test_normalize_repasse_mapeia_e_hash_deterministico() -> None:
    a = normalize_repasse(_record())
    b = normalize_repasse(_record())
    assert a.fonte == "fpm"
    assert a.natureza == "credito"
    assert a.valor == Decimal("1000.50")
    assert a.municipio_ibge == "3550308"
    assert a.proveniencia is not None and a.proveniencia["valor"] == "api"
    assert a.hash_conteudo == b.hash_conteudo  # determinístico
    c = normalize_repasse(_record(valor="2000"))
    assert c.hash_conteudo != a.hash_conteudo  # mudança material → hash muda


async def test_rls_isola_repasses_por_tenant(
    seed_user, seed_municipio, seed_repasse
) -> None:
    a = await seed_user("a@a.com")
    b = await seed_user("b@b.com")
    await seed_municipio(a, "2301109")
    await seed_municipio(b, "3550308")
    await seed_repasse("fpm", "A1", "2301109")
    await seed_repasse("fpm", "B1", "3550308")

    async with rls_session(a) as s:
        rows = await service.listar(s)
        assert {r.id_externo for r in rows} == {"A1"}
    async with rls_session(b) as s:
        rows = await service.listar(s)
        assert {r.id_externo for r in rows} == {"B1"}


async def test_visao_geral_liquido_credito_menos_deducao(
    seed_user, seed_municipio, seed_repasse
) -> None:
    u = await seed_user("c@c.com")
    await seed_municipio(u, "3550308")
    await seed_repasse("fpm", "cred", "3550308", valor="1000", natureza="credito")
    await seed_repasse("fpm", "ded", "3550308", valor="200", natureza="deducao")

    async with rls_session(u) as s:
        vg = await service.visao_geral(s, municipio="3550308")
    # líquido = 1000 - 200
    assert vg.total_pago == Decimal("800")
    assert vg.movimentacoes == 2
    assert vg.fontes[0].fonte == "fpm"
    assert len(vg.feed) == 1  # mesma data
    assert vg.feed[0].subtotal == Decimal("800")


class _MockFpm:
    source_id = "fpm"

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        return [
            RawRecord(
                source_id="fpm",
                id_externo="M1",
                municipio_ibge=municipio_ibge,
                raw={"data_repasse": "2026-06-10", "natureza": "credito", "valor": "500"},
            )
        ]

    async def health_check(self) -> bool:
        return True


async def test_sync_municipio_popula_e_fica_visivel(seed_user, monkeypatch) -> None:
    u = await seed_user("d@d.com")
    monkeypatch.setitem(cbase._registry, "fpm", _MockFpm())

    async with rls_session(u) as s:
        total = await service.sync_municipio(
            s, usuario_id=u, municipio_ibge="3106200", fontes=["fpm"]
        )
        assert total == 1
        rows = await service.listar(s, municipio="3106200")
        assert len(rows) == 1  # visível ao próprio usuário (municipio avulso gravado)
