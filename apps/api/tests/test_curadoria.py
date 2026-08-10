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


async def test_reonboarding_substitui_territorio(seed_user) -> None:
    """Ajustar perfil = refazer onboarding: a nova seleção SUBSTITUI a antiga
    (municípios monitorados fora dela saem e as buscas deles são desativadas)."""
    u = await seed_user("re@o.com")
    primeiro = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        areas=["saude"],
        monitorar_ativo=True,
    )
    segundo = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3304557", nome="Rio de Janeiro", uf="RJ")],
        areas=["educacao"],
        monitorar_ativo=True,
    )
    async with rls_session(u) as s:
        await onb_service.onboarding(s, usuario_id=u, req=primeiro)
        await onb_service.onboarding(s, usuario_id=u, req=segundo)
        rows = (await s.execute(select(MunicipioInteresse))).scalars().all()
        assert {r.ibge for r in rows} == {"3304557"}
        buscas = {b.municipio_ibge: b.ativo for b in await mon_service.listar_buscas(s, u)}
        assert buscas["3550308"] is False
        assert buscas["3304557"] is True


async def test_reonboarding_promove_avulso_e_preserva_cache(seed_user, seed_municipio) -> None:
    """Município já 'avulso' (cache da consulta avulsa) vira monitorado quando
    escolhido; os demais 'avulso' não são removidos pelo ajuste."""
    u = await seed_user("avulso@o.com")
    await seed_municipio(u, "3550308", modo="avulso")
    await seed_municipio(u, "2927408", modo="avulso")
    req = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        monitorar_ativo=False,
    )
    async with rls_session(u) as s:
        await onb_service.onboarding(s, usuario_id=u, req=req)
        rows = (await s.execute(select(MunicipioInteresse))).scalars().all()
        modos = {r.ibge: r.modo for r in rows}
        assert modos == {"3550308": "monitorado", "2927408": "avulso"}


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
    assert detect_changes.hash_mudou(None, "x") is False
    assert detect_changes.hash_mudou("a", "a") is False
    assert detect_changes.hash_mudou("a", "b") is True
    payload = detect_changes.montar_payload({"situacao": "Em análise"}, {"situacao": "Aprovada"})
    assert payload["mudou"]["situacao"] == {"antes": "Em análise", "depois": "Aprovada"}
    assert detect_changes.classificar(payload) == "status"
