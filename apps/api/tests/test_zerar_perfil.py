"""Zeragem do PRÓPRIO perfil (DELETE /profile) — a zona de perigo da conta.

Volta o usuário ao estado pré-onboarding: sem território, sem preferências e
sem curadoria. As propostas do território são zeradas por SOFT DELETE e os
demais caches perdem o frescor — nada é apagado, porque o cache é global e um
DELETE cascatearia nos favoritos/monitoramentos de OUTRO usuário que acompanhe
o mesmo município (a FK ignora RLS).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from src.db.session import rls_session
from src.services import consulta_avulsa
from src.services import perfil as service

from .conftest import _owner_engine


async def _seed_proposta(id_externo: str, ibge: str) -> uuid.UUID:
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


async def _curadoria(usuario_id: uuid.UUID, proposta_id: uuid.UUID) -> None:
    """Favorito + pasta + monitoramento + alerta, como o usuário teria acumulado."""
    async with _owner_engine.begin() as conn:
        # as tabelas por-tenant têm FORCE RLS → o seed precisa do tenant setado
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(usuario_id)}
        )
        await conn.execute(
            text("INSERT INTO favoritos (usuario_id, proposta_id) VALUES (:u,:p)"),
            {"u": usuario_id, "p": proposta_id},
        )
        await conn.execute(
            text("INSERT INTO pastas (usuario_id, nome) VALUES (:u,'Prioridades')"),
            {"u": usuario_id},
        )
        await conn.execute(
            text("INSERT INTO monitoramentos (usuario_id, proposta_id, ativo) VALUES (:u,:p,true)"),
            {"u": usuario_id, "p": proposta_id},
        )
        await conn.execute(
            text(
                "INSERT INTO monitoramentos_busca (usuario_id, municipio_ibge, ativo) "
                "VALUES (:u,'2611606',true)"
            ),
            {"u": usuario_id},
        )
        await conn.execute(
            text(
                "INSERT INTO alertas (usuario_id, proposta_id, tipo, lido) "
                "VALUES (:u,:p,'status',false)"
            ),
            {"u": usuario_id, "p": proposta_id},
        )


async def _preferencias(usuario_id: uuid.UUID) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(usuario_id)}
        )
        await conn.execute(
            text(
                "INSERT INTO preferencias_usuario (usuario_id, fontes, areas, monitorar_ativo) "
                "VALUES (:u, ARRAY['transferegov_ff'], ARRAY['saude'], true)"
            ),
            {"u": usuario_id},
        )


async def _contar(tabela: str, usuario_id: uuid.UUID | None = None) -> int:
    sql = f"SELECT count(*) FROM {tabela}"
    params: dict = {}
    if usuario_id is not None:
        sql += " WHERE usuario_id = :u"
        params["u"] = usuario_id
    async with _owner_engine.begin() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def _usuario_do_banco(usuario_id: uuid.UUID):
    """O objeto Usuario que o endpoint receberia do fastapi-users."""
    from sqlalchemy import select

    from src.models.usuario import Usuario

    async with rls_session(usuario_id) as s:
        return (await s.execute(select(Usuario).where(Usuario.id == usuario_id))).scalar_one()


async def test_zerar_perfil_apaga_territorio_preferencias_e_curadoria(
    seed_user, seed_municipio
) -> None:
    u = await seed_user("zera@x.com")
    await seed_municipio(u, "2611606")
    await seed_municipio(u, "3550308")  # mais de um município: todos vão embora
    await _preferencias(u)
    pid = await _seed_proposta("A1", "2611606")
    await _curadoria(u, pid)

    usuario = await _usuario_do_banco(u)
    async with rls_session(u) as s:
        resultado = await service.zerar(s, usuario)

    assert resultado.municipios == 2
    assert resultado.favoritos == 1 and resultado.pastas == 1
    assert resultado.monitoramentos == 2  # proposta monitorada + busca monitorada
    assert resultado.alertas == 1
    for tabela in (
        "municipios_interesse",
        "preferencias_usuario",
        "favoritos",
        "pastas",
        "monitoramentos",
        "monitoramentos_busca",
        "alertas",
    ):
        assert await _contar(tabela, u) == 0, tabela

    # o perfil volta ao ponto de partida: sem território, o app manda ao onboarding
    async with rls_session(u) as s:
        perfil = await service.get_perfil(s, usuario)
    assert perfil.municipios == [] and perfil.areas == [] and perfil.fontes == []


async def test_propostas_do_territorio_sao_zeradas_por_soft_delete(
    seed_user, seed_municipio
) -> None:
    u = await seed_user("cache@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("A2", "2611606")

    usuario = await _usuario_do_banco(u)
    async with rls_session(u) as s:
        resultado = await service.zerar(s, usuario)

    assert resultado.propostas == 1
    # a linha continua no banco…
    assert await _contar("propostas") == 1
    # …marcada como excluída e sem frescor: a próxima consulta vai à fonte
    async with _owner_engine.begin() as conn:
        ativas = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM propostas "
                    "WHERE excluido_em IS NULL AND cache_atualizado_em IS NOT NULL"
                )
            )
        ).scalar_one()
    assert ativas == 0


async def test_zerar_nao_toca_no_perfil_de_outro_usuario(seed_user, seed_municipio) -> None:
    """A garantia que define o desenho: município compartilhado é comum.

    Se a zeragem APAGASSE a proposta do cache global, o favorito/monitoramento
    do outro usuário sumiria por cascade (a FK não enxerga RLS).
    """
    eu = await seed_user("eu@x.com")
    outro = await seed_user("outro@x.com")
    await seed_municipio(eu, "2611606")
    await seed_municipio(outro, "2611606")  # mesmo município, outro tenant
    pid = await _seed_proposta("A3", "2611606")
    await _curadoria(eu, pid)
    await _curadoria(outro, pid)

    usuario = await _usuario_do_banco(eu)
    async with rls_session(eu) as s:
        await service.zerar(s, usuario)

    # o outro usuário continua com território e com a curadoria intacta —
    # é isso que o soft delete protege (um DELETE cascatearia nela)
    assert await _contar("municipios_interesse", outro) == 1
    assert await _contar("favoritos", outro) == 1
    assert await _contar("monitoramentos", outro) == 1
    assert await _contar("alertas", outro) == 1
    assert await _contar("propostas") == 1


async def test_zerar_esquece_a_memoria_de_coleta_do_territorio(seed_user, seed_municipio) -> None:
    u = await seed_user("coleta@x.com")
    await seed_municipio(u, "2611606")
    # coleta recente neste município e em outro que não é do usuário
    consulta_avulsa._marcar_tentativa("transferegov_ff", "2611606", ok=True)
    consulta_avulsa._marcar_tentativa("transferegov_ff", "3550308", ok=True)

    usuario = await _usuario_do_banco(u)
    async with rls_session(u) as s:
        await service.zerar(s, usuario)

    # o município zerado recoleta já na próxima busca…
    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "2611606") is False
    # …e o resto do processo segue com sua memória (não é um flush global)
    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "3550308") is True


async def test_zerar_perfil_vazio_nao_estoura(seed_user) -> None:
    """Usuário que nunca fez onboarding: nada a apagar, nada a invalidar."""
    u = await seed_user("vazio@x.com")
    await _seed_proposta("A4", "2611606")  # cache de terceiros, fora do território

    usuario = await _usuario_do_banco(u)
    async with rls_session(u) as s:
        resultado = await service.zerar(s, usuario)

    assert resultado.municipios == 0 and resultado.propostas == 0
    # sem território, um IN vazio não pode virar "zera tudo"
    async with _owner_engine.begin() as conn:
        intactas = (
            await conn.execute(text("SELECT count(*) FROM propostas WHERE excluido_em IS NULL"))
        ).scalar_one()
    assert intactas == 1
