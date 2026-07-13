"""Conformidade fiscal (CAUC/CAPAG): normalização/hash, RLS, resumo e sync."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from src.connectors import base as cbase
from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion.normalizer_conformidade import normalize_conformidade
from src.services import conformidade as service
from tests.conftest import _owner_engine


def _rec(numero: str, status: str, secao: str = "I - Adimplência") -> RawRecord:
    return RawRecord(
        source_id="siconfi",
        id_externo=f"cauc:3550308:{numero}",
        municipio_ibge="3550308",
        raw={
            "tipo": "cauc",
            "numero": numero,
            "secao": secao,
            "descricao": f"Requisito {numero}",
            "status": status,
            "orgao": "PGFN/RFB",
        },
    )


async def _seed(municipio: str, tipo: str, numero: str, status: str, secao: str) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO conformidades (municipio_ibge, tipo, numero, secao, status, "
                "cache_atualizado_em) VALUES (:m,:t,:n,:s,:st, now())"
            ),
            {"m": municipio, "t": tipo, "n": numero, "s": secao, "st": status},
        )


def test_normalize_conformidade_hash_deterministico() -> None:
    a = normalize_conformidade(_rec("1.1", "comprovado"))
    b = normalize_conformidade(_rec("1.1", "comprovado"))
    assert a.tipo == "cauc" and a.status == "comprovado" and a.orgao == "PGFN/RFB"
    assert a.hash_conteudo == b.hash_conteudo
    c = normalize_conformidade(_rec("1.1", "a_comprovar"))
    assert c.hash_conteudo != a.hash_conteudo


async def test_rls_isola_conformidade(seed_user, seed_municipio) -> None:
    a = await seed_user("a@a.com")
    b = await seed_user("b@b.com")
    await seed_municipio(a, "3550308")
    await seed_municipio(b, "3304557")
    await _seed("3550308", "cauc", "1.1", "comprovado", "I")
    await _seed("3304557", "cauc", "1.1", "a_comprovar", "I")

    async with rls_session(a) as s:
        rows = await service.listar(s)
        assert {r.municipio_ibge for r in rows} == {"3550308"}
    async with rls_session(b) as s:
        rows = await service.listar(s)
        assert {r.municipio_ibge for r in rows} == {"3304557"}


async def test_resumo_kpis_por_status_e_secao(seed_user, seed_municipio) -> None:
    u = await seed_user("c@c.com")
    await seed_municipio(u, "3550308")
    await _seed("3550308", "cauc", "1.1", "comprovado", "I - Adimplência")
    await _seed("3550308", "cauc", "1.2", "a_comprovar", "I - Adimplência")
    await _seed("3550308", "cauc", "3.1", "desativado", "III - Transparência")
    await _seed("3550308", "capag", "nota", "rating", "CAPAG")

    async with rls_session(u) as s:
        r = await service.resumo(s, municipio="3550308")
    assert r.total == 3  # só requisitos CAUC
    assert r.comprovados == 1 and r.a_comprovar == 1 and r.desativados == 1
    assert len(r.secoes) == 2
    assert r.capag is not None and r.capag.tipo == "capag"


class _MockSiconfi:
    source_id = "siconfi"

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        # devolve conformidades DO município sincronizado (como a fonte real)
        def _r(numero: str, status: str) -> RawRecord:
            return RawRecord(
                source_id="siconfi",
                id_externo=f"cauc:{municipio_ibge}:{numero}",
                municipio_ibge=municipio_ibge,
                raw={"tipo": "cauc", "numero": numero, "status": status, "secao": "I"},
            )

        return [_r("1.1", "comprovado"), _r("1.2", "a_comprovar")]

    async def health_check(self) -> bool:
        return True


async def test_sync_municipio_popula(seed_user, monkeypatch) -> None:
    u = await seed_user("d@d.com")
    monkeypatch.setitem(cbase._registry, "siconfi", _MockSiconfi())
    async with rls_session(u) as s:
        n = await service.sync_municipio(s, usuario_id=u, municipio_ibge="3106200")
        assert n == 2
        rows = await service.listar(s, municipio="3106200")
        assert len(rows) == 2
