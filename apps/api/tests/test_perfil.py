"""Navegação profile-centric: /perfil e /perfil/visao-geral.

Garante que a visão parte do PERFIL (território do usuário) e não da fonte:
as dimensões agregam só o que o RLS deixa o usuário ver, e o território de um
usuário não vaza para o outro.
"""

from __future__ import annotations

from sqlalchemy import text

from src.db.session import rls_session
from src.services import perfil as service
from tests.conftest import _owner_engine


async def _seed_pref(usuario_id, areas: list[str]) -> None:
    async with _owner_engine.begin() as conn:
        # preferencias_usuario tem FORCE RLS por usuario_id → setar tenant.
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"),
            {"uid": str(usuario_id)},
        )
        await conn.execute(
            text(
                "INSERT INTO preferencias_usuario (usuario_id, areas, monitorar_ativo) "
                "VALUES (:u, :a, true) ON CONFLICT (usuario_id) DO UPDATE SET areas = :a"
            ),
            {"u": usuario_id, "a": areas},
        )


async def test_perfil_reflete_territorio_e_areas(seed_user, seed_municipio) -> None:
    u = await seed_user("perfil@a.com", papel="parlamentar")
    await seed_municipio(u, "3550308")
    await _seed_pref(u, ["saude", "educacao"])

    async with rls_session(u) as s:
        p = await service.get_perfil(s, _FakeUser(u, "parlamentar"))
    assert p.papel == "parlamentar"
    assert {m.ibge for m in p.municipios} == {"3550308"}
    assert set(p.areas) == {"saude", "educacao"}


async def test_visao_geral_agrega_por_perfil_e_isola_por_rls(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    a = await seed_user("va@a.com")
    b = await seed_user("vb@b.com")
    await seed_municipio(a, "3550308")
    await seed_municipio(b, "3304557")
    await seed_proposta("transferegov_ff", "p1", "3550308")
    await seed_proposta("transferegov_ff", "p2", "3550308")
    await seed_repasse("fpm", "r1", "3550308", valor="500")
    await seed_proposta("transferegov_ff", "pb", "3304557")  # do outro usuário

    async with rls_session(a) as s:
        vg = await service.visao_geral(s, _FakeUser(a, "executivo"))

    dims = {d.chave: d for d in vg.dimensoes}
    assert set(dims) == {"captacao", "recebidos", "conformidade", "obras"}
    assert dims["captacao"].total == 2  # só as do território de A (não a de B)
    assert dims["recebidos"].total == 1
    assert dims["obras"].total == 0 and dims["obras"].destaque == "sem obras ainda"
    assert {m.ibge for m in vg.municipios} == {"3550308"}


class _FakeUser:
    """Stand-in do modelo Usuario (só os atributos que o serviço lê)."""

    def __init__(self, uid, papel: str) -> None:
        self.id = uid
        self.papel = papel
        self.nome = None
