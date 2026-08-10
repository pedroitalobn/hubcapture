"""Zeragem de propostas pelo admin (DELETE /admin/proposals).

O endpoint roda na sessão de PLATAFORMA (sem tenant) e `propostas` tem FORCE
RLS com SELECT por município do usuário: uma contagem via SELECT ali enxerga 0
linhas e o painel leria "0 removidas" com a tabela de fato apagada. A contagem
correta é o rowcount do próprio DELETE (policy FOR DELETE libera). Zerar também
precisa esquecer a memória de tentativa da busca ao vivo — senão "recomeçar a
coleta do zero" só recoletaria após o TTL de 6h.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from src.api.v1.admin_fontes import zerar_propostas
from src.db.session import SessionLocal
from src.services import consulta_avulsa

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


async def _zerar_como_plataforma():
    """Chama o endpoint com a mesma sessão da dependency `get_platform_db`."""
    async with SessionLocal() as session:
        async with session.begin():
            return await zerar_propostas(_admin=None, session=session)


async def test_zerar_reporta_o_total_apagado_mesmo_sem_tenant(seed_user, seed_municipio) -> None:
    u = await seed_user("adm@x.com")
    await seed_municipio(u, "2611606")
    await _seed_proposta("Z1", "2611606")
    await _seed_proposta("Z2", "3550308")  # fora do território de qualquer usuário

    resultado = await _zerar_como_plataforma()

    # a resposta reflete o que o DELETE apagou (não um SELECT cego pelo RLS)…
    assert resultado.removidas == 2
    # …e a tabela ficou vazia de verdade
    assert await _contar("propostas") == 0


async def test_zerar_cascateia_favoritos(seed_user, seed_municipio) -> None:
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
    assert await _contar("favoritos") == 0


async def test_zerar_esquece_tentativas_de_coleta() -> None:
    # simula uma coleta recente bem-sucedida: sem a limpeza, a busca ao vivo
    # pularia a fonte por até 6h e a "recoleta do zero" não aconteceria
    consulta_avulsa._marcar_tentativa("transferegov_ff", "2611606", ok=True)
    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "2611606") is True

    await _zerar_como_plataforma()

    assert consulta_avulsa._tentativa_fresca("transferegov_ff", "2611606") is False
