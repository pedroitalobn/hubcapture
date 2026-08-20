"""Onboarding, favoritos, pastas, monitoramentos, alertas e detect_changes."""

from __future__ import annotations

from sqlalchemy import select

from src.db.session import rls_session
from src.models.municipio_interesse import MunicipioInteresse
from src.schemas.curadoria import (
    MunicipioIn,
    OnboardingRequest,
    PastaCreate,
)
from src.services import (
    alertas as alertas_service,
)
from src.services import (
    detect_changes,
)
from src.services import (
    favoritos as fav_service,
)
from src.services import (
    monitoramentos as mon_service,
)
from src.services import (
    onboarding as onb_service,
)
from src.services import (
    pastas as pasta_service,
)


async def test_onboarding_persiste_municipios_e_preferencias(seed_user) -> None:
    u = await seed_user("o@o.com")
    req = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        fontes=["fpm", "emendas"],
        areas=["saude"],
        monitorar_ativo=True,
        papel="parlamentar",
        disparar_sync=False,
    )
    async with rls_session(u) as s:
        resp = await onb_service.onboarding(s, usuario_id=u, req=req)
        assert resp.municipios == 1
        rows = (await s.execute(select(MunicipioInteresse))).scalars().all()
        assert {r.ibge for r in rows} == {"3550308"}
        assert rows[0].modo == "monitorado"


async def test_favoritos_ciclo(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("f@f.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "P1", "3550308")
    from src.models.proposta import Proposta

    async with rls_session(u) as s:
        pid = (await s.execute(select(Proposta.id))).scalar_one()
        await fav_service.adicionar(s, u, pid)
        assert len(await fav_service.listar(s, u)) == 1
        await fav_service.adicionar(s, u, pid)  # idempotente
        assert len(await fav_service.listar(s, u)) == 1
        await fav_service.remover(s, u, pid)
        assert await fav_service.listar(s, u) == []


async def test_pastas_criar_e_vincular(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("pa@pa.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "P1", "3550308")
    from src.models.proposta import Proposta

    async with rls_session(u) as s:
        pid = (await s.execute(select(Proposta.id))).scalar_one()
        pasta = await pasta_service.criar(s, u, PastaCreate(nome="Saúde", cor="#f00"))
        await pasta_service.adicionar_proposta(s, pasta.id, pid)
        assert len(await pasta_service.listar(s, u)) == 1


async def test_alerta_gerado_apenas_se_monitorado(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("m@m.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "P1", "3550308")
    from src.models.proposta import Proposta

    async with rls_session(u) as s:
        pid = (await s.execute(select(Proposta.id))).scalar_one()
        # sem monitoramento → não gera
        a = await alertas_service.gerar_se_monitorado(s, u, pid, "status", {"x": 1})
        assert a is None
        # com monitoramento → gera
        await mon_service.criar(s, u, pid, ["painel"])
        a = await alertas_service.gerar_se_monitorado(s, u, pid, "status", {"x": 1})
        assert a is not None
        assert len(await alertas_service.listar(s, u)) == 1


def test_detect_changes_puro() -> None:
    """A detecção é por CRITÉRIO: o que mudou decide o tipo do alerta (§53)."""
    antes = {"situacao": "Em análise", "movimentacao": None}
    depois = {"situacao": "Aprovada", "movimentacao": None}
    (mudanca,) = detect_changes.avaliar(antes, depois, {"situacao"})
    assert mudanca.criterio == "situacao"
    assert mudanca.payload["mudou"]["situacao"] == {"antes": "Em análise", "depois": "Aprovada"}
    # critério desligado não vira alerta, mesmo com o campo tendo mudado
    assert detect_changes.avaliar(antes, depois, {"empenho"}) == []
