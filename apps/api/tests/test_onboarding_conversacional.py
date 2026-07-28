"""Onboarding conversacional: busca de municípios + feed de novidades do perfil.

A busca de municípios roda sem rede (o índice do IBGE é monkeypatched); o feed
de novidades usa o Postgres local com RLS, como os demais testes de perfil.
"""

from __future__ import annotations

from sqlalchemy import text

from src.db.session import rls_session
from src.services import municipios as municipios_service
from src.services import perfil as perfil_service
from src.services import primeiro_sync
from tests.conftest import _owner_engine


class _FakeUser:
    def __init__(self, uid, papel: str = "executivo") -> None:
        self.id = uid
        self.papel = papel
        self.nome = None


_MUNICIPIOS_FAKE = [
    {"ibge": "3550308", "nome": "São Paulo", "uf": "SP", "busca": "sao paulo"},
    {"ibge": "3304557", "nome": "Rio de Janeiro", "uf": "RJ", "busca": "rio de janeiro"},
    {"ibge": "2927408", "nome": "Salvador", "uf": "BA", "busca": "salvador"},
]


async def test_busca_municipio_por_nome_sem_acento(monkeypatch) -> None:
    async def _carregar_fake() -> list[dict]:
        return _MUNICIPIOS_FAKE

    monkeypatch.setattr(municipios_service, "_carregar", _carregar_fake)

    resultado = await municipios_service.buscar("São Pa")
    assert [m["ibge"] for m in resultado] == ["3550308"]
    # sem acento também encontra; código IBGE parcial idem
    assert (await municipios_service.buscar("sao paulo"))[0]["nome"] == "São Paulo"
    assert (await municipios_service.buscar("330"))[0]["ibge"] == "3304557"


async def test_busca_degrada_sem_ibge(monkeypatch) -> None:
    async def _carregar_quebrado() -> list[dict]:
        raise RuntimeError("IBGE fora do ar")

    monkeypatch.setattr(municipios_service, "_carregar", _carregar_quebrado)
    assert await municipios_service.buscar("São Paulo") == []


async def _seed_pref(usuario_id, *, fontes: list[str], areas: list[str]) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"),
            {"uid": str(usuario_id)},
        )
        await conn.execute(
            text(
                "INSERT INTO preferencias_usuario (usuario_id, fontes, areas, "
                "monitorar_ativo) VALUES (:u, :f, :a, true)"
            ),
            {"u": usuario_id, "f": fontes, "a": areas},
        )


async def test_novidades_recorta_por_fontes_e_areas_do_perfil(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await seed_user("nov@a.com")
    await seed_municipio(u, "3550308")
    # perfil: fonte explícita fpm + área saúde (que puxa fns)
    await _seed_pref(u, fontes=["fpm"], areas=["saude"])

    await seed_repasse("fpm", "r1", "3550308", valor="1000", data_repasse="2026-07-10")
    await seed_repasse("fns", "r2", "3550308", valor="2000", data_repasse="2026-07-20")
    await seed_repasse("fnde", "r3", "3550308", valor="3000")  # fora do recorte
    await seed_proposta("transferegov_ff", "p1", "3550308")  # fora do recorte

    async with rls_session(u) as s:
        nov = await perfil_service.novidades(s, _FakeUser(u))

    fontes = [i.fonte for i in nov.itens]
    assert set(fontes) == {"fpm", "fns"}
    # mais recente primeiro
    assert nov.itens[0].fonte == "fns"
    assert nov.itens[0].tipo == "recebido"


async def test_novidades_sem_preferencias_mostra_tudo_do_territorio(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    a = await seed_user("nova@a.com")
    b = await seed_user("novb@b.com")
    await seed_municipio(a, "3550308")
    await seed_municipio(b, "3304557")
    await seed_proposta("transferegov_ff", "p1", "3550308", titulo="Creche")
    await seed_repasse("fpm", "r1", "3550308")
    await seed_repasse("fpm", "rb", "3304557")  # de outro usuário

    async with rls_session(a) as s:
        nov = await perfil_service.novidades(s, _FakeUser(a))

    assert len(nov.itens) == 2  # RLS não vaza o repasse do território de B
    assert {i.tipo for i in nov.itens} == {"captacao", "recebido"}


def test_primeiro_sync_seleciona_fontes_pelo_perfil() -> None:
    assert primeiro_sync._fontes_captacao(["fpm", "transferegov_ff"]) == [
        "transferegov_ff"
    ]
    assert primeiro_sync._fontes_captacao([]) == ["transferegov_ff"]
    assert primeiro_sync._fontes_recebidos(["fns", "fpm"]) == ["fpm", "fns"]
    assert primeiro_sync._fontes_recebidos([]) == ["fpm", "emendas"]
    assert primeiro_sync._fontes_obras(["saude", "educacao"]) == ["simec", "sismob"]
    assert primeiro_sync._fontes_obras([]) == ["caixa", "simec", "sismob"]
