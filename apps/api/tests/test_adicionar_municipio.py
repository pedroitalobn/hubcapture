"""Adicionar município pela interface (POST /profile/municipalities) + busca offline.

Até aqui município só entrava pelo onboarding — e refazê-lo regrava áreas,
fontes e canais. A porta nova amplia o território respeitando o PLANO (§39):
a feature `municipios_adicionar` e o `municipios_max` (sem limite = ilimitado),
com a MESMA regra de limite do onboarding.

E a busca de municípios (que alimenta o onboarding e esta tela) não pode mais
devolver lista vazia quando o IBGE recusa a conexão: cai na malha offline.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text, update

from src.db.session import SessionLocal, rls_session
from src.models.usuario import Usuario
from src.schemas.curadoria import AdicionarMunicipiosRequest, MunicipioIn
from src.schemas.planos import PlanoCreate, PlanoLimites
from src.services import municipios as municipios_service
from src.services import onboarding as onboarding_service
from src.services import perfil as service
from src.services import plano_gates
from src.services import planos as planos_service

from .conftest import _owner_engine


async def _plano(limites: dict, slug: str) -> uuid.UUID:
    async with SessionLocal() as s:
        async with s.begin():
            plano = await planos_service.criar(
                s, PlanoCreate(nome=slug, slug=slug, limites=PlanoLimites(**limites))
            )
            return plano.id


async def _atribuir(usuario_id: uuid.UUID, plano_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await s.execute(
                update(Usuario).where(Usuario.id == usuario_id).values(plano_id=plano_id)
            )
    plano_gates.limpar_cache()


async def _usuario(usuario_id: uuid.UUID) -> Usuario:
    async with rls_session(usuario_id) as s:
        return (await s.execute(select(Usuario).where(Usuario.id == usuario_id))).scalar_one()


async def _contar(sql: str, params: dict) -> int:
    async with _owner_engine.begin() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


def _m(ibge: str, nome: str | None = None, uf: str | None = None) -> MunicipioIn:
    return MunicipioIn(ibge=ibge, nome=nome, uf=uf)


# ── Serviço ─────────────────────────────────────────────────────────────────
async def test_plano_ilimitado_adiciona_sem_refazer_onboarding(seed_user, seed_municipio) -> None:
    u = await seed_user("ilimitado@a.com")
    await _atribuir(u, await _plano({}, "business-t"))
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        r = await service.adicionar_municipios(
            s,
            usuario,
            [_m("2300903", "Apuiarés", "CE"), _m("2304400", "Fortaleza", "CE"), _m("3550308")],
        )
        await s.commit()

    assert [m.ibge for m in r.adicionados] == ["2300903", "2304400"]
    assert r.adicionados[0].nome == "Apuiarés" and r.adicionados[0].uf == "CE"
    assert r.ja_existiam == ["3550308"]  # já estava: não duplica nem conta
    assert r.territorio.pode_adicionar and r.territorio.maximo is None
    assert r.territorio.em_uso == 3
    total = await _contar("SELECT count(*) FROM municipios_interesse WHERE usuario_id=:u", {"u": u})
    assert total == 3
    # território monitorado → busca de futuras propostas para os novos
    buscas = await _contar(
        "SELECT count(*) FROM monitoramentos_busca WHERE usuario_id=:u", {"u": u}
    )
    assert buscas == 2


async def test_limite_do_plano_vale_como_no_onboarding(seed_user, seed_municipio) -> None:
    u = await seed_user("limite@a.com")
    await _atribuir(u, await _plano({"municipios_max": 2}, "start-t"))
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        with pytest.raises(onboarding_service.LimitePlanoExcedido):
            await service.adicionar_municipios(
                s, usuario, [_m("2300903", "Apuiarés"), _m("2304400", "Fortaleza")]
            )

    async with rls_session(u) as s:
        r = await service.adicionar_municipios(s, usuario, [_m("2300903", "Apuiarés")])
        await s.commit()
    assert r.territorio.restantes == 0
    assert not r.territorio.pode_adicionar and r.territorio.motivo == "limite_atingido"


async def test_plano_pode_desligar_a_adicao_pela_interface(seed_user) -> None:
    u = await seed_user("desligado@a.com")
    await _atribuir(u, await _plano({"features": {"municipios_adicionar": False}}, "sem-add"))
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        with pytest.raises(service.AdicaoNaoPermitida):
            await service.adicionar_municipios(s, usuario, [_m("2300903", "Apuiarés")])
        perfil = await service.get_perfil(s, usuario)
    assert not perfil.territorio.pode_adicionar
    assert perfil.territorio.motivo == "plano_nao_permite"


async def test_perfil_informa_quantos_ainda_cabem(seed_user, seed_municipio) -> None:
    u = await seed_user("cabem@a.com")
    await _atribuir(u, await _plano({"municipios_max": 5}, "cinco"))
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        perfil = await service.get_perfil(s, usuario)
    assert perfil.territorio.maximo == 5
    assert perfil.territorio.em_uso == 1 and perfil.territorio.restantes == 4
    assert perfil.territorio.pode_adicionar


async def test_ibge_nao_numerico_e_recusado() -> None:
    with pytest.raises(ValueError):
        AdicionarMunicipiosRequest(municipios=[{"ibge": "IBGE123"}])


# ── Router ──────────────────────────────────────────────────────────────────
async def test_rota_adiciona_e_agenda_a_coleta_so_dos_novos(
    seed_user, seed_municipio, monkeypatch
) -> None:
    import httpx

    from src.api.deps import get_rls_db
    from src.core.users import current_active_user
    from src.main import app
    from src.services import primeiro_sync

    u = await seed_user("rota@a.com")
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)
    agendados: list[list[str]] = []
    monkeypatch.setattr(
        primeiro_sync, "agendar", lambda _uid, ibges, _f, _a: agendados.append(ibges)
    )

    async def _sessao():
        async with rls_session(u) as s:
            yield s

    app.dependency_overrides[current_active_user] = lambda: usuario
    app.dependency_overrides[get_rls_db] = _sessao
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/api/v1/profile/municipalities",
                json={"municipios": [{"ibge": "2300903", "nome": "Apuiarés", "uf": "CE"}]},
            )
            assert r.status_code == 201, r.text
            assert r.json()["sync_disparado"] is True
            assert agendados == [["2300903"]]

            # repetir o mesmo município não dispara coleta de novo
            r = await c.post(
                "/api/v1/profile/municipalities", json={"municipios": [{"ibge": "2300903"}]}
            )
            assert r.status_code == 201 and r.json()["ja_existiam"] == ["2300903"]
            assert len(agendados) == 1

            r = await c.get("/api/v1/profile")
            assert {m["ibge"] for m in r.json()["municipios"]} == {"3550308", "2300903"}
    finally:
        app.dependency_overrides.clear()


async def test_rota_responde_403_no_limite(seed_user, seed_municipio) -> None:
    import httpx

    from src.api.deps import get_rls_db
    from src.core.users import current_active_user
    from src.main import app

    u = await seed_user("rota403@a.com")
    await _atribuir(u, await _plano({"municipios_max": 1}, "free-t"))
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)

    async def _sessao():
        async with rls_session(u) as s:
            yield s

    app.dependency_overrides[current_active_user] = lambda: usuario
    app.dependency_overrides[get_rls_db] = _sessao
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/api/v1/profile/municipalities", json={"municipios": [{"ibge": "2300903"}]}
            )
            assert r.status_code == 403
            assert r.json()["detail"].startswith("LIMITE_PLANO_MUNICIPIOS")
    finally:
        app.dependency_overrides.clear()


# ── Busca de municípios: lista INTERNA, sem depender do IBGE ───────────────
async def test_busca_usa_a_malha_interna_sem_rede(monkeypatch) -> None:
    """A busca não chama o IBGE: quando o gov.br recusava a conexão do
    servidor, ela devolvia lista vazia e o onboarding travava."""
    import httpx

    async def _sem_rede(*_a, **_k):
        raise AssertionError("a busca de municípios não pode sair para a rede")

    monkeypatch.setattr(httpx.AsyncClient, "send", _sem_rede)
    monkeypatch.setattr(municipios_service, "_cache", None)

    achados = await municipios_service.buscar("fortaleza")
    assert achados[0] == {"ibge": "2304400", "nome": "Fortaleza", "uf": "CE"}  # exato 1º
    assert (await municipios_service.buscar("apuiarez"))[0]["ibge"] == "2300903"
    # com erro de digitação, o nome mais próximo do digitado lidera
    assert (await municipios_service.buscar("fortalesa"))[0]["ibge"] == "2304400"
    assert (await municipios_service.buscar("2300903"))[0]["nome"] == "Apuiarés"
    assert await municipios_service.nome_uf_por_ibge("3550308") == ("São Paulo", "SP")


def test_malha_interna_tem_todos_os_municipios() -> None:
    malha = municipios_service.ler_malha()
    assert len(malha) == 5571
    assert len({m["ibge"] for m in malha}) == 5571
    assert all(len(m["ibge"]) == 7 and m["ibge"].isdigit() and m["uf"] for m in malha)
    # o prefixo do código é a UF — a mesma tabela que a saída usa offline
    assert all(municipios_service.uf_do_ibge(m["ibge"]) == m["uf"] for m in malha)


def test_dados_por_ibge_traz_os_identificadores_das_fontes() -> None:
    """Código → tudo o que as fontes pedem, sem rede: UF, IBGE de 6 dígitos,
    nome (Portal da Transparência), SIAFI (Tesouro) e a sede no mapa."""
    d = municipios_service.dados_por_ibge("2300903")
    assert d is not None
    assert (d.nome, d.uf, d.ibge6, d.siafi) == ("Apuiarés", "CE", "230090", "1317")
    assert d.latitude == pytest.approx(-3.94506) and d.longitude == pytest.approx(-39.4359)
    # o zero à esquerda do SIAFI faz parte do código
    assert municipios_service.dados_por_ibge("1100015").siafi == "0033"
    assert municipios_service.dados_por_ibge("9999999") is None


def test_malha_interna_tem_siafi_e_coordenadas_de_todos() -> None:
    malha = municipios_service.ler_malha()
    siafis = [m["siafi"] for m in malha]
    assert all(s and len(s) == 4 and s.isdigit() for s in siafis)
    assert len(set(siafis)) == len(malha)
    # sede dentro do território nacional
    assert all(-34 < m["latitude"] < 6 and -74 < m["longitude"] < -32 for m in malha)


def test_atualizar_malha_preserva_siafi_e_coordenadas(tmp_path, monkeypatch, capsys) -> None:
    """A API do IBGE não fornece SIAFI nem coordenadas: atualizar a malha não
    pode apagá-los, e município novo é apontado para completar à mão."""
    import shutil
    import sys

    from src.tools import atualizar_municipios as tool

    arquivo = tmp_path / "malha.csv"
    shutil.copy(municipios_service.ARQUIVO_MALHA, arquivo)
    atual = [(m["ibge"], m["nome"], m["uf"]) for m in municipios_service.ler_malha()]

    async def _ibge() -> list[tuple[str, str, str]]:
        return sorted([*atual, ("2399999", "Município Novo", "CE")])

    monkeypatch.setattr(tool, "ARQUIVO_MALHA", arquivo)
    monkeypatch.setattr(tool, "baixar", _ibge)
    monkeypatch.setattr(sys, "argv", ["atualizar_municipios"])
    assert tool.main() == 0

    nova = {m["ibge"]: m for m in municipios_service.ler_malha(arquivo)}
    assert len(nova) == 5572
    assert nova["2300903"]["siafi"] == "1317"
    assert nova["2300903"]["latitude"] == pytest.approx(-3.94506)
    assert nova["2399999"]["siafi"] is None and nova["2399999"]["latitude"] is None
    assert "2399999;Município Novo;CE" in capsys.readouterr().out
