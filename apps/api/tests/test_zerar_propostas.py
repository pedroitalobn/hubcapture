"""Zeragem de propostas pelo admin (DELETE /admin/proposals) — SOFT DELETE.

Zerar marca `excluido_em`; não apaga linha. Duas razões:
- as FKs são ON DELETE CASCADE e cascade IGNORA RLS, então um DELETE levaria
  junto favoritos, pastas e monitoramentos de qualquer usuário;
- soft delete é reversível (`POST /admin/proposals/restore`).

O endpoint roda na sessão de PLATAFORMA (sem tenant) e `propostas` tem FORCE
RLS por município: qualquer leitura ali enxerga 0 linhas. Por isso o UPDATE vai
SEM WHERE (não lê linha, então só a policy de UPDATE se aplica) e a contagem sai
do rowcount, nunca de um SELECT count(*).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from src.api.v1.admin_fontes import restaurar_propostas, zerar_propostas
from src.db.session import SessionLocal, rls_session
from src.models.proposta import Proposta
from src.schemas.proposta import PropostaCanonica
from src.services import consulta_avulsa
from src.services import propostas as prop_service

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


async def _contar(tabela: str) -> int:
    async with _owner_engine.begin() as conn:
        return (await conn.execute(text(f"SELECT count(*) FROM {tabela}"))).scalar_one()


async def _no_painel(usuario_id: uuid.UUID) -> int:
    """Quantas propostas o usuário enxerga — o que a tela mostraria."""
    async with rls_session(usuario_id) as s:
        return len(await prop_service.listar(s))


async def _zerar_como_plataforma():
    """Chama o endpoint com a mesma sessão da dependency `get_platform_db`."""
    async with SessionLocal() as session:
        async with session.begin():
            return await zerar_propostas(_admin=None, session=session)


async def _restaurar_como_plataforma():
    async with SessionLocal() as session:
        async with session.begin():
            return await restaurar_propostas(_admin=None, session=session)


async def test_zerar_reporta_o_total_e_some_do_painel(seed_user, seed_municipio) -> None:
    u = await seed_user("adm@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("Z1", "2611606")
    await _seed_proposta("Z2", "3550308")  # fora do território de qualquer usuário
    assert await _no_painel(u) == 1

    resultado = await _zerar_como_plataforma()

    # a resposta reflete o que o UPDATE marcou (não um SELECT cego pelo RLS)…
    assert resultado.removidas == 2
    # …a proposta sai do painel…
    assert await _no_painel(u) == 0
    # …mas continua no banco (soft delete)
    assert await _contar("propostas") == 2


async def test_zerar_preserva_a_curadoria_do_usuario(seed_user, seed_municipio) -> None:
    """O ganho do soft delete: sem DELETE não há cascade, então o favorito
    (e a pasta, e o monitoramento) do usuário sobrevive à zeragem."""
    u = await seed_user("adm2@x.com")
    await seed_municipio(u, "2611606")
    pid = await _seed_proposta("Z3", "2611606")
    async with _owner_engine.begin() as conn:
        # favoritos tem FORCE RLS FOR ALL → o seed precisa do tenant setado
        await conn.execute(text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(u)})
        await conn.execute(
            text("INSERT INTO favoritos (usuario_id, proposta_id) VALUES (:u,:p)"),
            {"u": u, "p": pid},
        )

    resultado = await _zerar_como_plataforma()

    assert resultado.removidas == 1
    assert await _contar("favoritos") == 1


async def test_coleta_ressuscita_proposta_zerada(seed_user, seed_municipio) -> None:
    """A fonte ainda publica a proposta → ela volta ao painel na recoleta.

    É por isso que o filtro de soft delete mora na consulta e não na policy de
    SELECT: o `ON CONFLICT DO UPDATE` valida a linha EXISTENTE contra o RLS, e
    escondê-la ali faria a coleta quebrar em vez de reativar o registro.
    """
    u = await seed_user("adm3@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("Z4", "2611606")
    await _zerar_como_plataforma()
    assert await _no_painel(u) == 0

    async with rls_session(u) as s:
        await prop_service.upsert(
            s,
            PropostaCanonica(
                fonte="transferegov_ff",
                id_externo="Z4",
                titulo="Proposta Z4 (recoletada)",
                municipio_ibge="2611606",
            ),
        )

    assert await _no_painel(u) == 1
    assert await _contar("propostas") == 1  # atualizou a mesma linha, não duplicou


async def test_restaurar_desfaz_a_zeragem(seed_user, seed_municipio) -> None:
    u = await seed_user("adm4@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("Z5", "2611606")
    await _zerar_como_plataforma()
    assert await _no_painel(u) == 0

    resultado = await _restaurar_como_plataforma()

    assert resultado.removidas == 1
    assert await _no_painel(u) == 1


async def test_zerada_nao_conta_como_cache_fresco(seed_user, seed_municipio) -> None:
    """Zerada não pode ser servida como cache fresco — senão a coleta seria
    pulada e o painel ficaria vazio até o TTL virar."""
    u = await seed_user("adm5@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("Z6", "2611606")
    await _zerar_como_plataforma()

    async with rls_session(u) as s:
        frescas = await consulta_avulsa._cache_fresco(s, "2611606", "transferegov_ff")
    assert frescas == []

    # e a linha zerada segue invisível numa contagem crua sob RLS
    async with rls_session(u) as s:
        visiveis = (
            await s.execute(
                select(func.count()).select_from(Proposta).where(Proposta.excluido_em.is_(None))
            )
        ).scalar_one()
    assert visiveis == 0


async def test_zerar_esquece_tentativas_de_coleta() -> None:
    # simula uma coleta recente bem-sucedida: sem a limpeza, a busca ao vivo
    # pularia a fonte por até 6h e a "recoleta do zero" não aconteceria
    consulta_avulsa._marcar_tentativa("transferegov_ff", "2611606", ok=True)
    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "2611606") is True

    await _zerar_como_plataforma()

    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "2611606") is False
