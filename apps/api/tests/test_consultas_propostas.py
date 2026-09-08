"""Consultas de propostas salvas — as abas do construtor (§61).

A aba é entidade PRÓPRIA e por-tenant: guarda o recorte com as mesmas chaves
dos query params de `GET /proposals`, sobrevive à troca de navegador e não
vaza para outro usuário.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.db.session import rls_session
from src.schemas.consultas import ConsultaCreate, ConsultaUpdate, FiltrosConsulta
from src.services import consultas_propostas as service


async def test_lista_vazia_ganha_aba_inicial(seed_user) -> None:
    """A tela nunca abre sem aba — fileira vazia lê como quebrada."""
    u = await seed_user("c1@c.com")
    async with rls_session(u) as s:
        abas = await service.garantir_padrao(s, u)
        assert [a.nome for a in abas] == [service.NOME_PADRAO]
        # idempotente: a segunda carga não cria outra
        assert len(await service.garantir_padrao(s, u)) == 1


async def test_aba_guarda_o_recorte_e_o_devolve(seed_user) -> None:
    u = await seed_user("c2@c.com")
    filtros = FiltrosConsulta(
        municipio=["2611606"], fonte=["transferegov"], ano=["2026"], q="creche"
    )
    async with rls_session(u) as s:
        aba = await service.criar(s, u, ConsultaCreate(nome="Apuiarés", filtros=filtros))
        assert aba.filtros["municipio"] == ["2611606"]
        lido = FiltrosConsulta.model_validate(aba.filtros)
    assert lido.q == "creche" and lido.ano == ["2026"]


async def test_uma_aba_por_municipio_e_a_ordem_da_fileira(seed_user) -> None:
    """O caso que motivou a entidade: uma aba por município do território."""
    u = await seed_user("c3@c.com")
    async with rls_session(u) as s:
        a = await service.criar(
            s, u, ConsultaCreate(nome="Apuiarés", filtros=FiltrosConsulta(municipio=["2611606"]))
        )
        b = await service.criar(
            s, u, ConsultaCreate(nome="Fortaleza", filtros=FiltrosConsulta(municipio=["2304400"]))
        )
        assert [c.ordem for c in (a, b)] == [0, 1]
        depois = await service.reordenar(s, u, [b.id, a.id])
        assert [c.nome for c in depois] == ["Fortaleza", "Apuiarés"]


async def test_reordenar_com_lista_incompleta_nao_apaga_aba(seed_user) -> None:
    u = await seed_user("c4@c.com")
    async with rls_session(u) as s:
        a = await service.criar(s, u, ConsultaCreate(nome="A"))
        await service.criar(s, u, ConsultaCreate(nome="B"))
        depois = await service.reordenar(s, u, [a.id])
        assert [c.nome for c in depois] == ["A", "B"]


async def test_atualizar_substitui_o_recorte_inteiro(seed_user) -> None:
    """Limpar um filtro é salvar o recorte sem ele — merge deixaria resíduo."""
    u = await seed_user("c5@c.com")
    async with rls_session(u) as s:
        aba = await service.criar(
            s,
            u,
            ConsultaCreate(nome="X", filtros=FiltrosConsulta(q="creche", tipo="disponivel")),
        )
        aba = await service.atualizar(
            s, aba, ConsultaUpdate(nome="Creches", filtros=FiltrosConsulta(q="creche"))
        )
    assert aba.nome == "Creches" and aba.filtros["tipo"] is None


async def test_aba_de_um_usuario_nao_aparece_para_outro(seed_user) -> None:
    dono = await seed_user("dono@c.com")
    outro = await seed_user("outro@c.com")
    async with rls_session(dono) as s:
        aba = await service.criar(s, dono, ConsultaCreate(nome="Só minha"))
    async with rls_session(outro) as s:
        assert await service.listar(s, outro) == []
        assert await service.obter(s, outro, aba.id) is None


async def test_remover_deixa_a_fileira_sem_a_aba(seed_user) -> None:
    u = await seed_user("c6@c.com")
    async with rls_session(u) as s:
        aba = await service.criar(s, u, ConsultaCreate(nome="Some"))
        await service.remover(s, aba)
        assert await service.listar(s, u) == []


async def test_limite_de_abas(seed_user, monkeypatch) -> None:
    u = await seed_user("c7@c.com")
    monkeypatch.setattr(service, "MAX_CONSULTAS", 2)
    async with rls_session(u) as s:
        await service.criar(s, u, ConsultaCreate(nome="1"))
        await service.criar(s, u, ConsultaCreate(nome="2"))
        with pytest.raises(service.LimiteConsultasExcedido):
            await service.criar(s, u, ConsultaCreate(nome="3"))


def test_filtro_desconhecido_e_recusado_ao_salvar() -> None:
    """Chave que a API não entende viraria aba que não filtra o que o gestor
    montou — melhor 422 na hora de salvar."""
    with pytest.raises(ValidationError):
        FiltrosConsulta.model_validate({"municipio_ibge": ["2611606"]})
    with pytest.raises(ValidationError):
        FiltrosConsulta.model_validate({"municipio": ["261160"]})  # IBGE de 6 dígitos


def test_router_inteiro_atras_do_modulo_captacao() -> None:
    """A aba é EXPLORAÇÃO (§40): desligar a captação tira o construtor."""
    from src.api.v1 import consultas_propostas as router_mod

    marcas = [str(d.dependency) for d in router_mod.router.dependencies]
    assert any("modulo" in m for m in marcas)


async def test_endpoints_das_abas_pela_rota_real(seed_user) -> None:
    """Exercita o ROUTER, não só o serviço (§52).

    Também é o teste de rota: `/proposals/views` precisa casar ANTES de
    `/proposals/{proposta_id}` — senão "views" viraria um UUID inválido e o
    construtor responderia 422 no lugar da lista de abas.
    """
    import httpx

    from src.api.deps import get_rls_db
    from src.core.users import current_active_user
    from src.main import app
    from src.models.usuario import Usuario

    u = await seed_user("rota@c.com")
    usuario = Usuario(id=u, email="rota@c.com", is_active=True, is_superuser=False)

    async def _sessao():
        async with rls_session(u) as s:
            yield s

    app.dependency_overrides[current_active_user] = lambda: usuario
    app.dependency_overrides[get_rls_db] = _sessao
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/api/v1/proposals/views")
            assert r.status_code == 200, r.text
            assert [a["nome"] for a in r.json()] == [service.NOME_PADRAO]

            r = await c.post(
                "/api/v1/proposals/views",
                json={"nome": "Apuiarés", "filtros": {"municipio": ["2611606"]}},
            )
            assert r.status_code == 201, r.text
            aba = r.json()
            assert aba["filtros"]["municipio"] == ["2611606"]

            r = await c.patch(
                f"/api/v1/proposals/views/{aba['id']}",
                json={"nome": "Apuiarés — creches", "filtros": {"q": "creche"}},
            )
            assert r.status_code == 200 and r.json()["filtros"]["q"] == "creche"
            # o recorte é substituído por inteiro: o município saiu junto
            assert r.json()["filtros"]["municipio"] == []

            # filtro que a API não conhece é recusado ao SALVAR
            r = await c.post(
                "/api/v1/proposals/views",
                json={"nome": "X", "filtros": {"municipio_ibge": ["2611606"]}},
            )
            assert r.status_code == 422

            r = await c.delete(f"/api/v1/proposals/views/{aba['id']}")
            assert r.status_code == 204
            r = await c.get("/api/v1/proposals/views")
            assert [a["nome"] for a in r.json()] == [service.NOME_PADRAO]
    finally:
        app.dependency_overrides.clear()
