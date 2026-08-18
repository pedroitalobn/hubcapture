"""Remover UM município do território (DELETE /profile/municipalities/{ibge}).

Ponto 01 do feedback do cliente: o onboarding só inseria município, e quem
errasse a cidade — ou deixasse de acompanhá-la — só tinha o `DELETE /profile`,
que zera o perfil inteiro. Esta é a saída cirúrgica.

O que estes testes travam: a remoção alcança só o TENANT e só aquele município,
o cache global não é tocado (é compartilhado com outros clientes e o cascade das
FKs ignora RLS — §41) e a memória de coleta em processo é esquecida, senão
readicionar a cidade abriria uma tela vazia por até 6h (§38).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from src.db.session import rls_session
from src.services import consulta_avulsa
from src.services import perfil as service

from .conftest import _owner_engine


async def _proposta(id_externo: str, ibge: str) -> uuid.UUID:
    pid = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (id, fonte, id_externo, titulo, municipio_ibge, "
                "cache_atualizado_em) VALUES (:id,'transferegov_ff',:e,:t,:ibge, now())"
            ),
            {"id": pid, "e": id_externo, "t": f"Proposta {id_externo}", "ibge": ibge},
        )
    return pid


async def _busca(usuario_id: uuid.UUID, ibge: str) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(usuario_id)}
        )
        await conn.execute(
            text(
                "INSERT INTO monitoramentos_busca (usuario_id, municipio_ibge, ativo) "
                "VALUES (:u,:ibge,true)"
            ),
            {"u": usuario_id, "ibge": ibge},
        )


async def _contar(sql: str, params: dict) -> int:
    async with _owner_engine.begin() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def _usuario(usuario_id: uuid.UUID):
    from sqlalchemy import select

    from src.models.usuario import Usuario

    async with rls_session(usuario_id) as s:
        return (await s.execute(select(Usuario).where(Usuario.id == usuario_id))).scalar_one()


async def test_remove_so_o_municipio_pedido(seed_user, seed_municipio) -> None:
    u = await seed_user("remove@a.com")
    await seed_municipio(u, "3550308")
    await seed_municipio(u, "2611606")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        resultado = await service.remover_municipio(s, usuario, "2611606")
        await s.commit()

    assert resultado.ibge == "2611606"
    restantes = await _contar(
        "SELECT count(*) FROM municipios_interesse WHERE usuario_id = :u", {"u": u}
    )
    assert restantes == 1


async def test_leva_junto_as_buscas_monitoradas_daquele_municipio(
    seed_user, seed_municipio
) -> None:
    """A busca do município removido viraria alerta de território que o usuário
    não acompanha mais — sai junto. A do outro município fica."""
    u = await seed_user("buscas@a.com")
    await seed_municipio(u, "3550308")
    await seed_municipio(u, "2611606")
    await _busca(u, "3550308")
    await _busca(u, "2611606")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        resultado = await service.remover_municipio(s, usuario, "2611606")
        await s.commit()

    assert resultado.buscas_monitoradas == 1
    sobrou = await _contar(
        "SELECT count(*) FROM monitoramentos_busca WHERE usuario_id = :u", {"u": u}
    )
    assert sobrou == 1


async def test_nao_apaga_o_cache_global_do_municipio(seed_user, seed_municipio) -> None:
    """A proposta é cache GLOBAL: outro cliente pode acompanhar a mesma cidade,
    e o cascade das FKs ignora RLS. Sair do território esconde — não apaga."""
    u = await seed_user("cache@a.com")
    await seed_municipio(u, "2611606")
    await _proposta("P-1", "2611606")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        await service.remover_municipio(s, usuario, "2611606")
        await s.commit()

    total = await _contar("SELECT count(*) FROM propostas WHERE municipio_ibge = '2611606'", {})
    assert total == 1
    excluidas = await _contar(
        "SELECT count(*) FROM propostas WHERE municipio_ibge = '2611606' "
        "AND excluido_em IS NOT NULL",
        {},
    )
    assert excluidas == 0


async def test_municipio_de_outro_usuario_nao_e_alcancado(seed_user, seed_municipio) -> None:
    u = await seed_user("dono@a.com")
    outro = await seed_user("outro@a.com")
    await seed_municipio(u, "3550308")
    await seed_municipio(outro, "3550308")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        await service.remover_municipio(s, usuario, "3550308")
        await s.commit()

    do_outro = await _contar(
        "SELECT count(*) FROM municipios_interesse WHERE usuario_id = :u", {"u": outro}
    )
    assert do_outro == 1


async def test_ibge_fora_do_territorio_e_erro_explicito(seed_user, seed_municipio) -> None:
    """Sem isto, remover um IBGE que não é do usuário responderia 'ok' tendo
    apagado nada — e a tela diria que removeu."""
    u = await seed_user("fora@a.com")
    await seed_municipio(u, "3550308")
    usuario = await _usuario(u)

    async with rls_session(u) as s:
        with pytest.raises(service.MunicipioNaoEncontrado):
            await service.remover_municipio(s, usuario, "9999999")


async def test_esquece_a_memoria_de_coleta_do_municipio(seed_user, seed_municipio) -> None:
    """Readicionar a cidade logo depois precisa recoletar de verdade (§38)."""
    u = await seed_user("memoria@a.com")
    await seed_municipio(u, "2611606")
    usuario = await _usuario(u)
    consulta_avulsa._TENTATIVAS[("transferegov_ff", "2611606")] = (9e9, True)

    async with rls_session(u) as s:
        await service.remover_municipio(s, usuario, "2611606")
        await s.commit()

    assert ("transferegov_ff", "2611606") not in consulta_avulsa._TENTATIVAS
