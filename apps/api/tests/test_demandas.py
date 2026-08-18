"""Central de demandas da Assessoria (ponto 20 do feedback).

O pedido do gestor deixa de morrer na conversa do WhatsApp: vira registro com
estado e histórico. O que estes testes travam: a demanda é do TENANT (o RLS não
deixa um usuário ver a do outro), o histórico acumula em vez de sobrescrever, a
fila da administração enxerga todo mundo, e situação inválida é recusada.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from src.db.session import plataforma_session, rls_session
from src.services import demandas as service

from .conftest import _owner_engine


async def _proposta(ibge: str = "3550308") -> uuid.UUID:
    pid = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (id, fonte, id_externo, titulo, municipio_ibge, "
                "cache_atualizado_em) VALUES (:id,'transferegov_ff','X','P',:ibge, now())"
            ),
            {"id": pid, "ibge": ibge},
        )
    return pid


async def test_demanda_nasce_aberta_com_historico(seed_user) -> None:
    u = await seed_user("demanda@a.com")
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Ajuda com o plano de trabalho", descricao="Dúvida")
        await s.commit()
        assert d.situacao == "aberta"
        assert d.historico and d.historico[0]["autor"] == "gestor"
        assert d.historico[0]["texto"] == "Dúvida"


async def test_gestor_nao_ve_demanda_de_outro(seed_user) -> None:
    """RLS por usuario_id: a fila de um não pode vazar para o outro."""
    a = await seed_user("a@a.com")
    b = await seed_user("b@a.com")
    async with rls_session(a) as s:
        await service.criar(s, a, assunto="Demanda do A")
        await s.commit()

    async with rls_session(b) as s:
        assert await service.listar(s) == []


async def test_historico_acumula_em_vez_de_sobrescrever(seed_user) -> None:
    """`historico` é jsonb: mutar a lista no lugar não marcaria o atributo como
    sujo e o append se perderia no commit."""
    u = await seed_user("hist@a.com")
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Assunto", descricao="Primeira")
        await service.comentar(s, d.id, texto="Segunda")
        await s.commit()

    async with rls_session(u) as s:
        d = (await service.listar(s))[0]
    assert [e["texto"] for e in d.historico] == ["Primeira", "Segunda"]


async def test_resolver_carimba_a_data(seed_user) -> None:
    u = await seed_user("resolve@a.com")
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Assunto")
        d = await service.comentar(s, d.id, texto="Resolvido", situacao="resolvida")
        await s.commit()
        assert d.situacao == "resolvida"
        assert d.resolvida_em is not None


async def test_filtro_de_abertas_esconde_o_que_terminou(seed_user) -> None:
    u = await seed_user("abertas@a.com")
    async with rls_session(u) as s:
        aberta = await service.criar(s, u, assunto="Em aberto")
        fechada = await service.criar(s, u, assunto="Fechada")
        await service.comentar(s, fechada.id, texto="fim", situacao="resolvida")
        await s.commit()

    async with rls_session(u) as s:
        vivas = await service.listar(s, incluir_resolvidas=False)
    assert [d.id for d in vivas] == [aberta.id]


async def test_situacao_invalida_e_recusada(seed_user) -> None:
    u = await seed_user("invalida@a.com")
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Assunto")
        with pytest.raises(service.SituacaoInvalida):
            await service.comentar(s, d.id, texto="x", situacao="arquivada")


async def test_demanda_inexistente_e_erro_explicito(seed_user) -> None:
    u = await seed_user("inexistente@a.com")
    async with rls_session(u) as s:
        with pytest.raises(service.DemandaNaoEncontrada):
            await service.comentar(s, uuid.uuid4(), texto="x")


async def test_fila_do_admin_ve_todos_os_tenants(seed_user) -> None:
    a = await seed_user("fila-a@a.com")
    b = await seed_user("fila-b@a.com")
    async with rls_session(a) as s:
        await service.criar(s, a, assunto="Do A")
        await s.commit()
    async with rls_session(b) as s:
        await service.criar(s, b, assunto="Do B")
        await s.commit()

    async with plataforma_session() as s:  # cross-tenant, como a administração
        fila = await service.listar_fila(s)
    assert {d.assunto for d, _ in fila} == {"Do A", "Do B"}
    assert {u.email for _, u in fila if u} == {"fila-a@a.com", "fila-b@a.com"}


async def test_resposta_da_assessoria_entra_como_assessoria(seed_user) -> None:
    u = await seed_user("resposta@a.com")
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Assunto")
        await s.commit()
        demanda_id = d.id

    async with plataforma_session() as s:
        await service.responder(s, demanda_id, texto="Estamos vendo", situacao="em_andamento")

    async with rls_session(u) as s:
        d = (await service.listar(s))[0]
    assert d.situacao == "em_andamento"
    assert d.historico[-1]["autor"] == "assessoria"


async def test_zerar_proposta_nao_leva_a_demanda_junto(seed_user) -> None:
    """A proposta é cache global e pode ser apagada; o pedido do gestor não pode
    ir junto — por isso a FK é SET NULL e não CASCADE."""
    u = await seed_user("fk@a.com")
    pid = await _proposta()
    async with rls_session(u) as s:
        d = await service.criar(s, u, assunto="Sobre a proposta", proposta_id=pid)
        await s.commit()
        demanda_id = d.id

    async with _owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM propostas WHERE id = :id"), {"id": pid})

    async with rls_session(u) as s:
        d = await service.obter(s, demanda_id)
    assert d.proposta_id is None
    assert d.assunto == "Sobre a proposta"
