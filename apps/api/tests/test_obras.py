"""Obras (execução — SISMOB/SIMEC/CAIXA): normalização/hash, RLS, resumo e sync."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from src.connectors import base as cbase
from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion.normalizer_obra import normalize_obra
from src.services import obras as service
from tests.conftest import _owner_engine


def _rec(fonte: str, ext: str, ibge: str, situacao: str, **extra) -> RawRecord:
    return RawRecord(
        source_id=fonte,
        id_externo=ext,
        municipio_ibge=ibge,
        raw={"nome": f"Obra {ext}", "situacao": situacao, "eixo": "saude", **extra},
    )


async def _seed(
    fonte: str, ext: str, ibge: str, situacao: str, invest: str = "100"
) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO obras (fonte, id_externo, municipio_ibge, situacao, "
                "valor_investimento, cache_atualizado_em) "
                "VALUES (:f,:e,:m,:s,:v, now())"
            ),
            {"f": fonte, "e": ext, "m": ibge, "s": situacao, "v": invest},
        )


def test_normalize_obra_hash_e_situacao() -> None:
    a = normalize_obra(_rec("sismob", "1", "3550308", "Em Execução"))
    b = normalize_obra(_rec("sismob", "1", "3550308", "em execucao"))
    assert a.fonte == "sismob" and a.situacao == "em_execucao"
    assert a.hash_conteudo == b.hash_conteudo  # variações de texto → mesmo canônico
    c = normalize_obra(_rec("sismob", "1", "3550308", "Concluída"))
    assert c.situacao == "concluida" and c.hash_conteudo != a.hash_conteudo


async def test_rls_isola_obras(seed_user, seed_municipio) -> None:
    a = await seed_user("oa@a.com")
    b = await seed_user("ob@b.com")
    await seed_municipio(a, "3550308")
    await seed_municipio(b, "3304557")
    await _seed("sismob", "x1", "3550308", "em_execucao")
    await _seed("simec", "x2", "3304557", "concluida")

    async with rls_session(a) as s:
        rows = await service.listar(s)
        assert {r.municipio_ibge for r in rows} == {"3550308"}
    async with rls_session(b) as s:
        rows = await service.listar(s)
        assert {r.municipio_ibge for r in rows} == {"3304557"}


async def test_resumo_kpis_por_situacao(seed_user, seed_municipio) -> None:
    u = await seed_user("oc@c.com")
    await seed_municipio(u, "3550308")
    await _seed("sismob", "1", "3550308", "em_execucao", invest="200")
    await _seed("simec", "2", "3550308", "concluida", invest="300")
    await _seed("caixa", "3", "3550308", "paralisada", invest="50")

    async with rls_session(u) as s:
        r = await service.resumo(s, municipio="3550308")
    assert r.total == 3
    assert r.em_execucao == 1 and r.concluidas == 1 and r.paralisadas == 1
    assert str(r.valor_investimento_total) == "550.00"
    assert len(r.por_situacao) == 3


class _MockObras:
    def __init__(self, source_id: str) -> None:
        self.source_id = source_id

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        return [
            _rec(self.source_id, f"{self.source_id}-1", municipio_ibge, "em_execucao"),
            _rec(self.source_id, f"{self.source_id}-2", municipio_ibge, "concluida"),
        ]

    async def health_check(self) -> bool:
        return True


async def test_sync_municipio_multi_fonte(seed_user, monkeypatch) -> None:
    u = await seed_user("od@d.com")
    for fonte in ("sismob", "simec", "caixa"):
        monkeypatch.setitem(cbase._registry, fonte, _MockObras(fonte))
    async with rls_session(u) as s:
        n = await service.sync_municipio(s, usuario_id=u, municipio_ibge="3106200")
        assert n == 6  # 3 fontes × 2 obras
        rows = await service.listar(s, municipio="3106200")
        assert len(rows) == 6


async def test_sync_fonte_com_falha_nao_derruba_as_outras(
    seed_user, monkeypatch
) -> None:
    u = await seed_user("oe@e.com")

    class _Quebrada:
        source_id = "sismob"

        async def collect(self, municipio_ibge: str, since: date):
            raise RuntimeError("fonte fora do ar")

        async def health_check(self) -> bool:
            return False

    monkeypatch.setitem(cbase._registry, "sismob", _Quebrada())
    monkeypatch.setitem(cbase._registry, "simec", _MockObras("simec"))
    monkeypatch.setitem(cbase._registry, "caixa", _MockObras("caixa"))
    async with rls_session(u) as s:
        n = await service.sync_municipio(s, usuario_id=u, municipio_ibge="3106200")
        assert n == 4  # sismob falhou; simec+caixa entregaram 2 cada
