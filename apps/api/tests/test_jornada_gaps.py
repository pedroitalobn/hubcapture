"""Gaps do fluxograma da jornada: tipo cadastrada/disponível, filtros por valor,
prazos estruturados, limite de plano, monitoramento de futuras propostas
(buscas), alertas de oportunidade e notícias (parse RSS)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from src.db.session import rls_session
from src.models.alerta import Alerta
from src.models.monitoramento import MonitoramentoBusca
from src.schemas.curadoria import MunicipioIn, OnboardingRequest
from src.services import monitoramentos as mon_service
from src.services import oportunidades as oport_service
from src.services import propostas as prop_service
from src.services.noticias import parse_rss
from src.services.onboarding import LimitePlanoExcedido
from src.services.onboarding import onboarding as onboarding_service

from .conftest import _owner_engine


# ── classificador cadastrada × disponível (puro) ────────────────────────────
def test_classificar_tipo() -> None:
    assert prop_service.classificar_tipo("Disponível para propostas") == "disponivel"
    assert prop_service.classificar_tipo("Em divulgação") == "disponivel"
    assert prop_service.classificar_tipo("Edital aberto") == "disponivel"
    assert prop_service.classificar_tipo("Proposta cadastrada") == "cadastrada"
    assert prop_service.classificar_tipo("Empenhada") == "cadastrada"
    assert prop_service.classificar_tipo(None) == "cadastrada"


# ── parse do RSS de notícias (puro) ─────────────────────────────────────────
def test_parse_rss_noticias() -> None:
    xml = (
        "<rss><channel>"
        "<item><title>Novo edital</title><link>https://gov.br/1</link>"
        "<description>desc</description></item>"
        "<item><title>Sem link</title></item>"
        "</channel></rss>"
    )
    noticias = parse_rss(xml)
    assert len(noticias) == 1
    assert noticias[0].titulo == "Novo edital"
    assert noticias[0].resumo == "desc"


# ── filtros por valor e tipo ────────────────────────────────────────────────
async def _seed_proposta_completa(
    fonte: str,
    id_externo: str,
    ibge: str,
    *,
    valor: str = "100000",
    situacao: str = "Empenhada",
    prazos: str | None = None,
) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                "valor_total, situacao, prazos, cache_atualizado_em) "
                "VALUES (:f,:e,'P',:ibge,:v,:s,CAST(:p AS jsonb), now())"
            ),
            {
                "f": fonte,
                "e": id_externo,
                "ibge": ibge,
                "v": valor,
                "s": situacao,
                "p": prazos,
            },
        )


async def test_listar_filtra_valor_e_tipo(seed_user, seed_municipio) -> None:
    u = await seed_user("valores@x.com")
    await seed_municipio(u, "3550308")
    await _seed_proposta_completa(
        "transferegov_ff", "A", "3550308", valor="50000", situacao="Empenhada"
    )
    await _seed_proposta_completa(
        "transferegov_ff",
        "B",
        "3550308",
        valor="900000",
        situacao="Disponível para propostas",
    )
    async with rls_session(u) as s:
        todas = await prop_service.listar(s)
        assert len(todas) == 2
        caras = await prop_service.listar(s, valor_min=100000)
        assert [p.id_externo for p in caras] == ["B"]
        disponiveis = await prop_service.listar(s, tipo="disponivel")
        assert [p.id_externo for p in disponiveis] == ["B"]
        cadastradas = await prop_service.listar(s, tipo="cadastrada")
        assert [p.id_externo for p in cadastradas] == ["A"]


async def test_listar_por_prazo(seed_user, seed_municipio) -> None:
    from datetime import date, timedelta

    u = await seed_user("prazos@x.com")
    await seed_municipio(u, "3550308")
    perto = (date.today() + timedelta(days=5)).isoformat()
    longe = (date.today() + timedelta(days=200)).isoformat()
    await _seed_proposta_completa(
        "transferegov_ff",
        "PZ1",
        "3550308",
        prazos=f'[{{"tipo": "envio", "data_limite": "{perto}"}}]',
    )
    await _seed_proposta_completa(
        "transferegov_ff",
        "PZ2",
        "3550308",
        prazos=f'[{{"tipo": "envio", "data_limite": "{longe}"}}]',
    )
    async with rls_session(u) as s:
        vencendo = await prop_service.listar_por_prazo(s, dias=30)
        assert len(vencendo) == 1
        proposta, prazos = vencendo[0]
        assert proposta.id_externo == "PZ1"
        assert prazos[0]["data_limite"] == perto


# ── enforcement do plano (tiers × municípios) ───────────────────────────────
async def test_onboarding_respeita_limite_do_plano(seed_user) -> None:
    u = await seed_user("plano@x.com")
    plano_id = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO planos (id, nome, slug, limites, ativo) "
                "VALUES (:id,'Basico','basico', CAST(:lim AS jsonb), true)"
            ),
            {"id": plano_id, "lim": '{"municipios_max": 1}'},
        )
        await conn.execute(
            text("UPDATE usuarios SET plano_id = :p WHERE id = :u"),
            {"p": plano_id, "u": u},
        )
    req = OnboardingRequest(
        municipios=[
            MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP"),
            MunicipioIn(ibge="3304557", nome="Rio de Janeiro", uf="RJ"),
        ],
        monitorar_ativo=False,
    )
    async with rls_session(u) as s:
        try:
            await onboarding_service(s, usuario_id=u, req=req)
            raise AssertionError("deveria ter estourado o limite do plano")
        except LimitePlanoExcedido as exc:
            assert exc.maximo == 1

    # dentro do limite passa
    req_ok = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        monitorar_ativo=False,
    )
    async with rls_session(u) as s:
        resp = await onboarding_service(s, usuario_id=u, req=req_ok)
        assert resp.municipios == 1


# ── onboarding cria buscas de futuras propostas + grava WhatsApp ────────────
async def test_onboarding_cria_busca_e_whatsapp(seed_user) -> None:
    u = await seed_user("wpp@x.com")
    req = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        monitorar_ativo=True,
        telefone_wpp="+5511912345678",
        optin_wpp=True,
        canais_alerta=["painel", "email"],
    )
    async with rls_session(u) as s:
        await onboarding_service(s, usuario_id=u, req=req)
        buscas = await mon_service.listar_buscas(s, u)
        assert len(buscas) == 1
        assert buscas[0].municipio_ibge == "3550308"
        assert set(buscas[0].canais or []) == {"painel", "email", "wpp"}
    async with _owner_engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT telefone_wpp, optin_wpp FROM usuarios WHERE id = :u"),
                {"u": u},
            )
        ).one()
        assert row.telefone_wpp == "+5511912345678"
        assert row.optin_wpp is True


# ── varredura: nova proposta para busca ativa ───────────────────────────────
async def test_varredura_detecta_nova_proposta(seed_user, seed_municipio) -> None:
    from src.models.usuario import Usuario

    u = await seed_user("busca@x.com")
    await seed_municipio(u, "3550308")
    async with rls_session(u) as s:
        await mon_service.criar_busca(
            s, u, municipio_ibge="3550308", area=None, fonte=None, canais=["painel"]
        )
    # proposta entra no cache DEPOIS da criação da busca
    await _seed_proposta_completa("transferegov_ff", "NOVA", "3550308")
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        criados = await oport_service.varredura(s, usuario)
        assert criados >= 1
        alertas = (
            (await s.execute(select(Alerta).where(Alerta.tipo == "nova_proposta"))).scalars().all()
        )
        assert len(alertas) == 1
        assert alertas[0].payload["fonte"] == "transferegov_ff"
        busca = (await s.execute(select(MonitoramentoBusca))).scalar_one()
        assert busca.ultimo_alerta_em is not None

    # segunda varredura não duplica (cursor avançou)
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        await oport_service.varredura(s, usuario)
        alertas = (
            (await s.execute(select(Alerta).where(Alerta.tipo == "nova_proposta"))).scalars().all()
        )
        assert len(alertas) == 1


# ── varredura: oportunidade (repasse sem proposta cadastrada) ───────────────
async def test_varredura_detecta_oportunidade(seed_user, seed_municipio, seed_repasse) -> None:
    from src.models.usuario import Usuario

    u = await seed_user("oport@x.com")
    await seed_municipio(u, "3550308")
    await seed_repasse("fns", "R1", "3550308", valor="500000")
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        criados = await oport_service.varredura(s, usuario)
        assert criados == 1
        alerta = (await s.execute(select(Alerta).where(Alerta.tipo == "oportunidade"))).scalar_one()
        assert alerta.proposta_id is None
        assert alerta.payload["fonte"] == "fns"

        # dedupe: rodar de novo com o alerta ainda não lido não duplica
        criados2 = await oport_service.varredura(s, usuario)
        assert criados2 == 0


# ── busca em tempo real (live-search multi-fonte, best-effort) ──────────────
async def test_live_search_usa_cache_fresco_e_reporta_erro(
    seed_user, seed_municipio
) -> None:
    from src.services import consulta_avulsa as ca

    u = await seed_user("live@x.com")
    await seed_municipio(u, "3550308")
    # cache FRESCO da fonte ff → live_search responde sem ir à rede
    await _seed_proposta_completa("transferegov_ff", "LV1", "3550308")

    async with rls_session(u) as s:
        rows, status = await ca.live_search(
            s, usuario_id=u, fonte="transferegov_ff"
        )
        assert [p.id_externo for p in rows] == ["LV1"]
        assert status == [
            {"fonte": "transferegov_ff", "municipio_ibge": "3550308", "status": "ok"}
        ]

    # fonte desconhecida → status de erro, sem derrubar a busca
    async with rls_session(u) as s:
        rows, status = await ca.live_search(s, usuario_id=u, fonte="nao_existe")
        assert status[0]["status"] == "erro"


def test_fontes_alvo_prioriza_filtro_area_perfil() -> None:
    from src.services.consulta_avulsa import CAPTACAO_FONTES, _fontes_alvo

    assert _fontes_alvo("fns", None, None) == ["fns"]
    assert _fontes_alvo(None, "saude", None) == ["fns"]
    assert _fontes_alvo(None, None, ["fnde", "fpm"]) == ["fnde"]
    assert _fontes_alvo(None, None, None) == list(CAPTACAO_FONTES)
