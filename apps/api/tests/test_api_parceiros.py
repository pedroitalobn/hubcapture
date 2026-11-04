"""API de integração para parceiros + sandbox (§67).

Cobre as três camadas: a CHAVE (formato, hash, ambiente, revogação, dono
admin), o LIMITE (por minuto/dia, teto global, concorrência, política de
rotas) e o SANDBOX (nenhuma saída externa, dados fictícios, reset). Os testes
HTTP usam a autenticação real — nada de override de usuário quando quem entra
é a chave.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text

from src.core import limite_api
from src.core.config import settings
from src.core.limite_api import Limitador, motivo_bloqueio
from src.db.session import SessionLocal, rls_session
from src.main import app
from src.models.api_chave import ApiUso
from src.models.favorito import Favorito
from src.models.proposta import Proposta
from src.models.usuario import Usuario
from src.services import api_chaves
from src.services import sandbox as sandbox_service

from .conftest import _owner_engine


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _usuario(uid: uuid.UUID) -> Usuario:
    async with SessionLocal() as s:
        return await s.get(Usuario, uid)


async def _chave(uid: uuid.UUID, **kw) -> str:
    async with SessionLocal() as s:
        async with s.begin():
            _, texto = await api_chaves.criar(s, await _usuario(uid), nome="Teste", **kw)
    return texto


async def _plano(uid: uuid.UUID, limites: str) -> None:
    pid = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO planos (id, nome, slug, limites, ativo) "
                "VALUES (:id,'P',:slug, CAST(:lim AS jsonb), true)"
            ),
            {"id": pid, "slug": f"p-{pid.hex[:6]}", "lim": limites},
        )
        await conn.execute(
            text("UPDATE usuarios SET plano_id = :p WHERE id = :u"), {"p": pid, "u": uid}
        )
    from src.services import plano_gates

    plano_gates.limpar_cache()


# ── Chave ───────────────────────────────────────────────────────────────────
def test_formato_hash_e_ambiente() -> None:
    texto, prefixo, h = api_chaves.gerar("live")
    assert api_chaves.FORMATO.match(texto)
    assert texto.startswith(prefixo) and prefixo.startswith("hub_live_")
    assert len(h) == 64 and h == api_chaves.hash_de(texto)
    assert api_chaves.ambiente_da_chave(texto) == "live"
    assert api_chaves.ambiente_da_chave(api_chaves.gerar("test")[0]) == "test"
    assert api_chaves.ambiente_da_chave("hub_live_curta") is None
    assert api_chaves.gerar()[0] != api_chaves.gerar()[0]


async def test_admin_nao_recebe_chave(seed_user) -> None:
    uid = await seed_user("adm@x.com")
    async with _owner_engine.begin() as conn:
        await conn.execute(text("UPDATE usuarios SET is_superuser=true WHERE id=:u"), {"u": uid})
    with pytest.raises(api_chaves.ChaveInvalida):
        await _chave(uid)


# ── Política de rotas ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("metodo", "caminho", "query", "escopo", "esperado"),
    [
        ("GET", "/api/v1/proposals", "", "leitura", None),
        ("GET", "/api/v1/transfers/overview", "municipio=2304400", "leitura", None),
        ("GET", "/api/v1/users/me", "", "leitura", None),
        ("PATCH", "/api/v1/users/me", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("GET", "/api/v1/users/123", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("GET", "/api/v1/admin/users", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("POST", "/api/v1/auth/login", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("POST", "/api/v1/account/api-keys", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("POST", "/api/v1/copilot/island", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("POST", "/api/v1/proposals/live-search", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("POST", "/api/v1/transfers/sync", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("GET", "/api/v1/proposals/x/documents/y/file", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        ("DELETE", "/api/v1/profile", "", "escrita", "API_ROTA_NAO_DISPONIVEL"),
        (
            "GET",
            "/api/v1/proposals/x/timeline",
            "atualizar=true",
            "escrita",
            "API_COLETA_AO_VIVO_NAO_DISPONIVEL",
        ),
        ("GET", "/api/v1/proposals/x/timeline", "atualizar=false", "leitura", None),
        ("POST", "/api/v1/favorites", "", "leitura", "API_CHAVE_SOMENTE_LEITURA"),
        ("POST", "/api/v1/favorites", "", "escrita", None),
        ("POST", "/api/v1/developer/sandbox/reset", "", "escrita", None),
        ("GET", "/health", "", "leitura", None),
    ],
)
def test_politica_de_rotas(metodo, caminho, query, escopo, esperado) -> None:
    assert motivo_bloqueio(metodo, caminho, query, escopo) == esperado


# ── Limitador ───────────────────────────────────────────────────────────────
class _Relogio:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 4, 12, 0, 5, tzinfo=UTC).timestamp()

    def __call__(self) -> float:
        return self.t


def test_limite_por_minuto_e_virada_de_janela() -> None:
    relogio = _Relogio()
    lim = Limitador(relogio)
    k = uuid.uuid4()
    for _ in range(3):
        d = lim.entrar(k, 3, 100)
        assert d.ok
        lim.sair(k)
    d = lim.entrar(k, 3, 100)
    assert not d.ok and d.codigo == "API_LIMITE_MINUTO" and d.retry_after == 55
    relogio.t += 60  # próxima janela
    assert lim.entrar(k, 3, 100).ok


def test_cota_diaria_e_semente_apos_restart() -> None:
    lim = Limitador(_Relogio())
    k = uuid.uuid4()
    lim.semear_dia(k, 99)  # o processo reiniciou depois de 99 chamadas hoje
    assert lim.entrar(k, 1000, 100).ok
    lim.sair(k)
    d = lim.entrar(k, 1000, 100)
    assert not d.ok and d.codigo == "API_LIMITE_DIARIO"


def test_teto_global_soma_todas_as_chaves(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_limite_global_por_minuto", 4)
    lim = Limitador(_Relogio())
    for _ in range(4):
        k = uuid.uuid4()
        assert lim.entrar(k, 10, 100).ok
        lim.sair(k)
    d = lim.entrar(uuid.uuid4(), 10, 100)
    assert not d.ok and d.codigo == "API_LIMITE_GLOBAL"


def test_concorrencia_por_chave_e_total(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_max_simultaneas", 3)
    monkeypatch.setattr(settings, "api_max_simultaneas_por_chave", 2)
    lim = Limitador(_Relogio())
    a, b = uuid.uuid4(), uuid.uuid4()
    assert lim.entrar(a, 100, 1000).ok
    assert lim.entrar(a, 100, 1000).ok
    assert lim.entrar(a, 100, 1000).codigo == "API_SIMULTANEAS"  # 3ª da mesma chave
    assert lim.entrar(b, 100, 1000).ok
    assert lim.entrar(b, 100, 1000).codigo == "API_SIMULTANEAS"  # 4ª no total
    lim.sair(a)
    assert lim.entrar(b, 100, 1000).ok  # a vaga devolvida volta a valer


# ── Ponta a ponta (autenticação real) ───────────────────────────────────────
async def test_chave_entra_como_a_conta_e_respeita_o_territorio(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("parceiro@x.com")
    outro = await seed_user("outro@x.com")
    await seed_municipio(u, "2304400")
    await seed_municipio(outro, "3550308")
    await seed_proposta("transferegov_disc", "A1", "2304400", titulo="Minha")
    await seed_proposta("transferegov_disc", "B1", "3550308", titulo="Alheia")
    chave = await _chave(u)

    async with _cliente() as c:
        r = await c.get("/api/v1/developer/me", headers={"X-API-Key": chave})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["autenticacao"] == "api_key" and corpo["email"] == "parceiro@x.com"
        assert corpo["municipios"] == ["2304400"]
        assert corpo["chave"]["escopo"] == "leitura"
        assert r.headers["X-RateLimit-Limit"] == str(settings.api_limite_por_minuto)
        assert int(r.headers["X-RateLimit-Remaining"]) == settings.api_limite_por_minuto - 1

        # o RLS de sempre: só o território da conta dona da chave
        r = await c.get("/api/v1/proposals", headers={"X-API-Key": chave})
        assert r.status_code == 200, r.text
        assert [p["titulo"] for p in r.json()["itens"]] == ["Minha"]

        # Bearer hub_… também serve
        r = await c.get("/api/v1/users/me", headers={"Authorization": f"Bearer {chave}"})
        assert r.status_code == 200 and r.json()["email"] == "parceiro@x.com"

        # leitura não escreve; chave não alcança admin nem coleta ao vivo
        r = await c.post(
            "/api/v1/favorites",
            headers={"X-API-Key": chave},
            json={"proposta_id": str(uuid.uuid4())},
        )
        assert r.status_code == 403 and r.json()["detail"] == "API_CHAVE_SOMENTE_LEITURA"
        r = await c.get("/api/v1/admin/api-keys", headers={"X-API-Key": chave})
        assert r.status_code == 403 and r.json()["detail"] == "API_ROTA_NAO_DISPONIVEL"
        r = await c.get("/api/v1/proposals/deadlines?atualizar=true", headers={"X-API-Key": chave})
        assert r.json()["detail"] == "API_COLETA_AO_VIVO_NAO_DISPONIVEL"

        # inválida, de outro ambiente, e revogada
        falsa = api_chaves.gerar("live")[0]
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": falsa})
        assert r.status_code == 401 and r.json()["detail"] == "API_CHAVE_INVALIDA"
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": api_chaves.gerar("test")[0]})
        assert r.status_code == 401 and r.json()["detail"] == "API_CHAVE_AMBIENTE_ERRADO"

        async with SessionLocal() as s:
            async with s.begin():
                ids = [c.id for c, _ in await api_chaves.listar(s, u)]
                assert await api_chaves.revogar(s, ids[0], usuario_id=u)
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": chave})
        assert r.status_code == 401


async def test_conta_desativada_perde_acesso(seed_user) -> None:
    u = await seed_user("inativo@x.com")
    chave = await _chave(u)
    async with _owner_engine.begin() as conn:
        await conn.execute(text("UPDATE usuarios SET is_active=false WHERE id=:u"), {"u": u})
    api_chaves.limpar_cache()
    async with _cliente() as c:
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": chave})
    assert r.status_code == 401


async def test_limite_por_minuto_responde_429_e_grava_consumo(seed_user) -> None:
    u = await seed_user("limite@x.com")
    chave = await _chave(u, limite_por_minuto=2)
    async with _cliente() as c:
        for _ in range(2):
            r = await c.get("/api/v1/users/me", headers={"X-API-Key": chave})
            assert r.status_code == 200
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": chave})
    assert r.status_code == 429
    assert r.json()["detail"] == "API_LIMITE_MINUTO"
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-RateLimit-Remaining"] == "0"

    await limite_api.gravar_consumo()
    async with SessionLocal() as s:
        linha = (await s.execute(select(ApiUso))).scalar_one()
    assert (linha.requisicoes, linha.bloqueadas) == (2, 1)


async def test_painel_jwt_nao_passa_pelo_limite(seed_user, monkeypatch) -> None:
    """Sem chave, o middleware não interfere (o painel dos gestores segue igual)."""
    monkeypatch.setattr(settings, "api_limite_global_por_minuto", 0)
    async with _cliente() as c:
        r = await c.get("/api/v1/users/me")
    assert r.status_code == 401  # o 401 normal do fastapi-users, não um 429
    assert "X-RateLimit-Limit" not in r.headers


async def test_conta_emite_chave_conforme_o_plano(seed_user) -> None:
    from src.core.users import current_active_user

    u = await seed_user("conta@x.com")
    usuario = await _usuario(u)
    app.dependency_overrides[current_active_user] = lambda: usuario
    try:
        async with _cliente() as c:
            r = await c.get("/api/v1/account/api-keys")
            assert r.status_code == 200 and r.json()["disponivel"] is False
            r = await c.post("/api/v1/account/api-keys", json={"nome": "ERP"})
            assert r.status_code == 403

            await _plano(u, '{"features": {"api": true}, "api_chaves_max": 1, "api_req_min": 30}')
            usuario = await _usuario(u)  # agora com o plano (cada request relê o usuário)
            app.dependency_overrides[current_active_user] = lambda: usuario
            r = await c.post("/api/v1/account/api-keys", json={"nome": "ERP", "escopo": "escrita"})
            assert r.status_code == 201, r.text
            criada = r.json()
            assert criada["chave"].startswith("hub_live_")
            assert criada["limite_por_minuto"] == 30 and criada["escopo"] == "escrita"

            r = await c.post("/api/v1/account/api-keys", json={"nome": "Outra"})
            assert r.status_code == 403
            assert r.json()["detail"].startswith("LIMITE_PLANO_API_CHAVES")

            r = await c.get("/api/v1/account/api-keys")
            lista = r.json()["chaves"]
            assert len(lista) == 1 and "chave" not in lista[0]
            assert lista[0]["prefixo"] == criada["prefixo"]

            r = await c.delete(f"/api/v1/account/api-keys/{criada['id']}")
            assert r.status_code == 204
            r = await c.get("/api/v1/account/api-keys")
            assert r.json()["chaves"][0]["ativa"] is False
    finally:
        app.dependency_overrides.pop(current_active_user, None)


# ── Sandbox ─────────────────────────────────────────────────────────────────
@pytest.fixture
def modo_sandbox(monkeypatch):
    monkeypatch.setattr(settings, "sandbox", True)
    api_chaves.limpar_cache()
    yield
    api_chaves.limpar_cache()


async def test_sandbox_bloqueia_saida_externa(monkeypatch) -> None:
    from src.core.sandbox import SaidaBloqueadaSandbox, instalar_bloqueio

    monkeypatch.setattr(settings, "sandbox_hosts_permitidos", "permitido.exemplo")
    desfazer = instalar_bloqueio()
    try:
        async with httpx.AsyncClient() as c:
            with pytest.raises(SaidaBloqueadaSandbox):
                await c.get("https://api.transferegov.gestao.gov.br/")
            # é uma ConnectError: o tratamento de "fonte fora do ar" já a absorve
            with pytest.raises(httpx.ConnectError):
                await c.get("https://exemplo.com/")
        with pytest.raises(SaidaBloqueadaSandbox):
            httpx.Client().get("https://exemplo.com/")
        async with _cliente() as c:  # transporte em memória segue funcionando
            assert (await c.get("/health")).status_code == 200
    finally:
        desfazer()


async def test_sandbox_nao_envia_email_whatsapp_nem_push(modo_sandbox) -> None:
    from src.notifications import email, uniq, webpush

    assert await email.enviar("a@b.com", "x", "y") is False
    assert await uniq.enviar("+5585999999999", "oi") is False
    assert await webpush.enviar("https://fcm.googleapis.com/x", "k", "a", {}) is False


def test_dados_ficticios_deterministicos_e_relativos_a_hoje() -> None:
    hoje = date(2026, 11, 4)
    p1, r1 = sandbox_service.dados_ficticios("2304400", "Fortaleza", "CE", hoje)
    p2, r2 = sandbox_service.dados_ficticios("2304400", "Fortaleza", "CE", hoje)
    assert [p.model_dump() for p in p1] == [p.model_dump() for p in p2]
    assert all(p.titulo.startswith("[SANDBOX]") for p in p1)
    assert all(p.dados_fonte["sandbox"] for p in p1)
    assert all(r.descricao.startswith("[SANDBOX]") for r in r1)
    # o prazo mais próximo cai dentro de 30 dias (alimenta /proposals/deadlines)
    proximos = [date.fromisoformat(p.prazos[0]["data_limite"]) for p in p1]
    assert min(proximos) - hoje <= timedelta(days=30)
    # repasses dos últimos 3 meses, inclusive virando o ano
    _, r_jan = sandbox_service.dados_ficticios("2304400", None, None, date(2027, 1, 15))
    assert {r.competencia for r in r_jan} == {"2027-01", "2026-12", "2026-11"}


async def test_sandbox_ponta_a_ponta(seed_user, modo_sandbox) -> None:
    from src.services import modulos

    async with SessionLocal() as s:  # recebidos nasce desligado (§29)
        async with s.begin():
            await modulos.definir(s, "recebidos", True)
    modulos.limpar_cache()
    u = await seed_user("integrador@x.com")
    chave = await _chave(u, escopo="escrita")
    assert chave.startswith("hub_test_")
    n = await sandbox_service.preparar_conta(u)
    assert n == len(sandbox_service.MUNICIPIOS_PADRAO)

    async with _cliente() as c:
        # chave de produção não vale no sandbox
        r = await c.get("/api/v1/users/me", headers={"X-API-Key": api_chaves.gerar("live")[0]})
        assert r.json()["detail"] == "API_CHAVE_AMBIENTE_ERRADO"

        r = await c.get("/api/v1/developer/me", headers={"X-API-Key": chave})
        assert r.json()["sandbox"] is True and len(r.json()["municipios"]) == 3

        r = await c.get("/api/v1/proposals?limite=100", headers={"X-API-Key": chave})
        assert r.status_code == 200, r.text
        itens = r.json()["itens"]
        assert r.json()["total"] == 3 * len(sandbox_service._OBJETOS)
        assert all(p["titulo"].startswith("[SANDBOX]") for p in itens)

        r = await c.get("/api/v1/transfers", headers={"X-API-Key": chave})
        assert r.status_code == 200 and r.json()

        r = await c.get("/api/v1/alerts", headers={"X-API-Key": chave})
        assert r.status_code == 200 and len(r.json()) == 2

        # o parceiro mexe nos dados e depois zera tudo
        r = await c.post(
            "/api/v1/favorites", headers={"X-API-Key": chave}, json={"proposta_id": itens[0]["id"]}
        )
        assert r.status_code == 201, r.text
        r = await c.post("/api/v1/developer/sandbox/reset", headers={"X-API-Key": chave})
        assert r.status_code == 200, r.text

    async with rls_session(u) as s:
        favoritos = (await s.execute(select(func.count()).select_from(Favorito))).scalar_one()
        propostas = (await s.execute(select(func.count()).select_from(Proposta))).scalar_one()
    assert favoritos == 0
    assert propostas == 3 * len(sandbox_service._OBJETOS)


async def test_sandbox_primeiro_sync_semeia_o_territorio_escolhido(
    seed_user, seed_municipio, modo_sandbox
) -> None:
    from src.services import primeiro_sync

    u = await seed_user("onb@x.com")
    await seed_municipio(u, "2611606")
    await primeiro_sync.executar(u, ["2611606"], ["transferegov_disc"], [])
    async with rls_session(u) as s:
        ibges = set((await s.execute(select(Proposta.municipio_ibge))).scalars().all())
    assert ibges == {"2611606"}  # o território da conta, não o padrão


async def test_reset_de_sandbox_fora_do_sandbox_e_404(seed_user) -> None:
    from src.core.users import current_active_user

    u = await seed_user("prod@x.com")
    usuario = await _usuario(u)
    app.dependency_overrides[current_active_user] = lambda: usuario
    try:
        async with _cliente() as c:
            r = await c.post("/api/v1/developer/sandbox/reset")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(current_active_user, None)
