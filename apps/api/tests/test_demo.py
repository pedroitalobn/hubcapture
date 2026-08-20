"""Acesso DEMO: conta semeada, sandbox sem erro e pacote inicial do Class.

O demo é um usuário comum (`is_demo`) apontando para municípios que já têm
dados no cache. O que se garante aqui:
- boot/`/auth/demo` criam e semeiam a conta (território + curadoria) uma vez;
- a busca ao vivo NUNCA vai à fonte na sessão demo (`somente_cache`) — nem
  com `forcar` — então fonte fora do ar não vira erro na apresentação;
- escrita destrutiva/de identidade responde 403 `DEMO_SOMENTE_LEITURA`;
- o Class virgem ganha o pacote inicial (artigos publicados + hints válidos),
  sem nunca sobrescrever curadoria existente do admin.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from starlette.requests import Request

from src.db.session import SessionLocal, rls_session
from src.models.favorito import Favorito
from src.models.helpdesk import HelpdeskArtigo, HelpdeskHint, HelpdeskModulo
from src.models.municipio_interesse import MunicipioInteresse
from src.models.pasta import Pasta
from src.models.usuario import Usuario
from src.services import consulta_avulsa
from src.services import demo as demo_service
from src.services import helpdesk as helpdesk_service
from src.services import perfil as perfil_service


async def _seed_cache(seed_proposta) -> None:
    """Cache com dois municípios — Petrolina/PE com mais propostas."""
    for n in range(3):
        await seed_proposta(
            "transferegov_disc",
            f"pe-{n}",
            "2611101",
            titulo=f"Proposta {n}",
            municipio_nome="Petrolina",
            uf="PE",
            data_proposta=date(2026, 1, 10 + n),
        )
    await seed_proposta(
        "transferegov_ff",
        "sp-1",
        "3550308",
        municipio_nome="São Paulo",
        uf="SP",
        data_proposta=date(2026, 2, 1),
    )


async def test_ensure_demo_semeia_territorio_e_curadoria(seed_proposta) -> None:
    await _seed_cache(seed_proposta)
    user = await demo_service.ensure_demo()
    assert user is not None and user.is_demo and user.is_active

    async with rls_session(user.id) as s:
        municipios = set(
            (
                await s.execute(
                    select(MunicipioInteresse.ibge).where(MunicipioInteresse.usuario_id == user.id)
                )
            ).scalars()
        )
        favoritos = (
            await s.execute(
                select(func.count()).select_from(Favorito).where(Favorito.usuario_id == user.id)
            )
        ).scalar_one()
        pastas = list(
            (await s.execute(select(Pasta.nome).where(Pasta.usuario_id == user.id))).scalars()
        )
    # o município com MAIS propostas no cache lidera o território do demo
    assert "2611101" in municipios and "3550308" in municipios
    assert favoritos > 0
    assert "Prioridades" in pastas

    # idempotente: segunda passada não duplica nada
    de_novo = await demo_service.ensure_demo()
    assert de_novo is not None and de_novo.id == user.id
    async with rls_session(user.id) as s:
        favoritos_2 = (
            await s.execute(
                select(func.count()).select_from(Favorito).where(Favorito.usuario_id == user.id)
            )
        ).scalar_one()
    assert favoritos_2 == favoritos


async def test_perfil_do_demo_carrega_a_flag(seed_proposta) -> None:
    await _seed_cache(seed_proposta)
    user = await demo_service.ensure_demo()
    async with SessionLocal() as s:
        usuario = await demo_service.usuario_demo(s)
    assert usuario is not None
    async with rls_session(user.id) as s:
        perfil = await perfil_service.get_perfil(s, usuario)
    assert perfil.demo is True
    assert perfil.municipios  # o demo nunca abre sem território quando há cache


async def test_auth_demo_emite_tokens_e_respeita_flag() -> None:
    from src.api.v1.auth import login_demo
    from src.services import config as config_service

    pair = await login_demo()
    assert pair.access_token and pair.refresh_token

    # desligado no painel → o endpoint some (404), sem tocar a conta existente
    async with SessionLocal() as s:
        async with s.begin():
            await config_service.definir(s, "demo_ativo", "off")
    with pytest.raises(HTTPException) as exc:
        await login_demo()
    assert exc.value.status_code == 404


async def test_demo_disponivel_no_ui() -> None:
    # sem conta demo ainda → o /login não mostra o botão
    assert await demo_service.demo_disponivel() is False
    await demo_service.ensure_demo()
    assert await demo_service.demo_disponivel() is True


async def test_bloqueio_de_escrita_da_conta_demo() -> None:
    demo = Usuario(email="d@d.app", hashed_password="x", is_demo=True)
    comum = Usuario(email="c@c.app", hashed_password="x", is_demo=False)

    with pytest.raises(HTTPException) as exc:
        demo_service.bloquear_escrita(demo)
    assert exc.value.status_code == 403
    assert exc.value.detail == demo_service.DEMO_SOMENTE_LEITURA
    demo_service.bloquear_escrita(comum)  # usuário comum passa

    def _req(metodo: str) -> Request:
        return Request({"type": "http", "method": metodo, "headers": []})

    # dependency de router: escrita bloqueada, leitura liberada
    with pytest.raises(HTTPException):
        await demo_service.negar_escrita_demo(_req("POST"), demo)
    await demo_service.negar_escrita_demo(_req("GET"), demo)
    await demo_service.negar_escrita_demo(_req("POST"), comum)
    await demo_service.negar_escrita_demo(_req("DELETE"), None)  # sem token: 401 vem da auth


async def test_endpoints_destrutivos_recusam_demo(seed_proposta) -> None:
    from src.api.v1.perfil import remover_municipio, zerar_perfil

    await _seed_cache(seed_proposta)
    user = await demo_service.ensure_demo()
    async with SessionLocal() as s:
        usuario = await demo_service.usuario_demo(s)
    assert usuario is not None

    async with rls_session(user.id) as s:
        with pytest.raises(HTTPException) as exc:
            await zerar_perfil(user=usuario, session=s)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await remover_municipio("2611101", user=usuario, session=s)
        assert exc.value.status_code == 403

    # o território sobreviveu intacto ao ataque de clique
    async with rls_session(user.id) as s:
        n = (
            await s.execute(
                select(func.count(MunicipioInteresse.id)).where(
                    MunicipioInteresse.usuario_id == user.id
                )
            )
        ).scalar_one()
    assert n == 2


async def test_sync_ativo_vira_no_op_para_demo() -> None:
    from src.api.v1.conformidade import SyncConformidadeRequest, conformidade_sync
    from src.api.v1.obras import obras_sync
    from src.api.v1.repasses import SyncRepassesRequest, sync_repasses

    demo = Usuario(email="d@d.app", hashed_password="x", is_demo=True)
    resp = await sync_repasses(
        SyncRepassesRequest(municipio_ibge="2611101"), user=demo, session=None
    )
    assert resp["demo"] is True and resp["gravados"] == 0
    resp = await conformidade_sync(
        SyncConformidadeRequest(municipio_ibge="2611101"), user=demo, session=None
    )
    assert resp["demo"] is True
    from src.api.v1.obras import SyncObrasRequest

    resp = await obras_sync(SyncObrasRequest(municipio_ibge="2611101"), user=demo, session=None)
    assert resp["demo"] is True


async def test_live_search_demo_nunca_consulta_fonte(
    monkeypatch, seed_user, seed_municipio, seed_proposta
) -> None:
    """`somente_cache` vence até o `forcar`: nenhuma fonte é chamada e todo par
    sai como status 'cache' — zero chance de erro de fonte na apresentação."""

    async def _explode(*_a, **_k):
        raise AssertionError("a sessão demo não pode ir à fonte")

    monkeypatch.setattr(consulta_avulsa, "_coletar", _explode)

    uid = await seed_user("gestor@x.gov.br")
    await seed_municipio(uid, "2611101")
    await seed_proposta("transferegov_ff", "p1", "2611101", titulo="UBS")

    async with rls_session(uid) as s:
        rows, total, status_fontes = await consulta_avulsa.live_search(
            s,
            usuario_id=uid,
            municipio=["2611101"],
            fonte="transferegov_ff",
            forcar=True,
            somente_cache=True,
        )
    assert total == 1 and rows
    assert status_fontes and all(f["status"] == "cache" for f in status_fontes)


async def test_semear_class_uma_vez_e_com_hints_validos() -> None:
    assert await demo_service.semear_class() is True
    async with SessionLocal() as s:
        artigos = list((await s.execute(select(HelpdeskArtigo))).scalars().unique())
        hints = list((await s.execute(select(HelpdeskHint))).scalars())
        modulos = list((await s.execute(select(HelpdeskModulo))).scalars().unique())
    assert len(artigos) == len(demo_service._CLASS_ARTIGOS)
    assert all(a.publicado for a in artigos)
    assert modulos and modulos[0].publicado
    assert any(a.modulo_id for a in artigos)  # o módulo tem aulas de verdade
    # toda hint plantada existe no catálogo (o ⓘ realmente aparece na tela)
    assert hints and all(helpdesk_service.chave_valida(h.chave) for h in hints)
    assert {h.chave for h in hints} >= {"proposta.empenhado", "funding.tipo"}

    # segunda passada: não duplica (o Class já tem conteúdo)
    assert await demo_service.semear_class() is False
    async with SessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(HelpdeskArtigo))).scalar_one()
    assert n == len(artigos)


async def test_semear_class_nao_sobrescreve_curadoria_do_admin() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            s.add(HelpdeskArtigo(titulo="Meu artigo", slug="meu-artigo", publicado=True))
    assert await demo_service.semear_class() is False
    async with SessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(HelpdeskArtigo))).scalar_one()
    assert n == 1  # só o artigo do admin — o seed não entrou por cima


async def test_video_do_class_quando_configurado() -> None:
    from src.models.helpdesk import HelpdeskMidia
    from src.services import config as config_service

    async with SessionLocal() as s:
        async with s.begin():
            await config_service.definir(
                s, "demo_video_url", "https://www.youtube.com/watch?v=exemplo"
            )
    assert await demo_service.semear_class() is True
    async with SessionLocal() as s:
        videos = list(
            (await s.execute(select(HelpdeskMidia).where(HelpdeskMidia.tipo == "video"))).scalars()
        )
    assert videos and all(v.url for v in videos)
