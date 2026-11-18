"""White label (§69): tema → CSS, resolução por host, domínio próprio, cadastro
pela marca e a identidade que assina e-mail, PDF, push e Copiloto."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

from src.ai import agent
from src.core.users import current_active_user, current_superuser
from src.db.session import SessionLocal
from src.main import app
from src.models.convite import Convite
from src.models.usuario import Usuario
from src.notifications import email_templates
from src.schemas.marcas import TemaMarca
from src.services import config as config_service
from src.services import dominios, identidade, marcas, oportunidades, pdf

from .conftest import _owner_engine

# PNG 1×1 válido (assinatura + IHDR + IDAT + IEND)
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


# ── Tema → CSS (puro) ───────────────────────────────────────────────────────


def test_tema_padrao_nao_emite_css() -> None:
    assert marcas.montar_css(TemaMarca()) == ""


def test_cores_viram_tokens_nos_dois_temas() -> None:
    tema = TemaMarca(cores={"acento": "#FF5500", "escuro": "#101030", "acao": "#123"})
    css = marcas.montar_css(tema)
    assert "--color-accent:#ff5500" in css
    assert "--action-bg:#112233" in css  # #123 expandido
    # tema escuro: o acento assume a ação e o trilho vira o tom escuro
    assert css.startswith("html:root{")
    assert '@media (prefers-color-scheme: dark){html:root:not([data-theme="light"]){' in css
    assert 'html:root[data-theme="dark"]{' in css
    assert "--nav-bg:#101030" in css
    # tinta escolhida por contraste: laranja claro leva tinta escura, não branca
    assert "--fill-accent-fg:#101030" in css


def test_preview_fica_escopado_e_religa_os_aliases() -> None:
    css = marcas.montar_css(TemaMarca(cores={"acento": "#ff5500"}), seletor=".marca-preview")
    assert ".marca-preview{" in css and "html:root" not in css
    assert "--color-brand:var(--brand)" in css
    assert ':root[data-theme="dark"] .marca-preview{' in css


def test_forma_fontes_titulos_e_icones() -> None:
    tema = TemaMarca(
        forma="pilula",
        fonte_corpo="poppins",
        fonte_titulo="playfair-display",
        titulos_caixa_alta=False,
        icones="grosso",
        icones_cantos="reto",
    )
    css = marcas.montar_css(tema)
    assert "--radius-control:999px" in css
    assert '--font-sans:"Poppins"' in css and '--font-display:"Playfair Display"' in css
    assert "serif" in css.split("--font-display:")[1].split(";")[0]
    assert "text-transform:none" in css
    assert "--icon-stroke:2.0" in css and "--icon-cap:square" in css
    urls = marcas.fontes_google(tema)
    assert len(urls) == 1 and "family=Poppins" in urls[0] and "Playfair+Display" in urls[0]


def test_fonte_enviada_vira_font_face() -> None:
    css = marcas.montar_css(
        TemaMarca(fonte_corpo="arquivo"), fontes_enviadas={"corpo": "/api/v1/x.woff2"}
    )
    assert '@font-face{font-family:"MarcaCorpo";src:url("/api/v1/x.woff2")' in css
    # "arquivo" sem arquivo enviado não sobrescreve nada
    assert marcas.montar_css(TemaMarca(fonte_corpo="arquivo")) == ""


@pytest.mark.parametrize(
    "dados",
    [
        {"cores": {"acento": "red"}},
        {"cores": {"acento": "#ff00"}},
        {"cores": {"acento": "#ff0000;}body{display:none"}},
        {"fonte_corpo": "comic-sans"},
        {"css_livre": "body{}"},
        {"forma": "estrela"},
    ],
)
def test_tema_recusa_o_que_nao_e_catalogo(dados) -> None:
    with pytest.raises(ValidationError):
        TemaMarca.model_validate(dados)


def test_avisos_de_contraste() -> None:
    avisos = marcas.avisos_de_contraste(TemaMarca(cores={"acao": "#9fe0c0", "escuro": "#8090a0"}))
    assert any("cor de ação" in a for a in avisos)
    assert any("tom escuro" in a for a in avisos)


# ── Hosts, slugs, domínios (puro) ───────────────────────────────────────────


def test_normalizar_host() -> None:
    assert marcas.normalizar_host("Painel.Exemplo.com.br:443.") == "painel.exemplo.com.br"
    assert marcas.normalizar_host("a.hub.com, proxy.interno") == "a.hub.com"
    assert marcas.normalizar_host(None) == ""


def test_slug_reservado_e_invalido() -> None:
    from fastapi import HTTPException

    assert marcas.validar_slug("Gabinete-Digital") == "gabinete-digital"
    for ruim in ("www", "api", "ab", "-abc", "abc-", "a_b", "a--b"):
        with pytest.raises(HTTPException):
            marcas.validar_slug(ruim)


def test_dominio_valida_e_recusa_o_da_plataforma() -> None:
    from fastapi import HTTPException

    base = "hubcapture.com.br"
    assert marcas.validar_dominio("https://Painel.Prefeitura.gov.br/x", base) == (
        "painel.prefeitura.gov.br"
    )
    assert marcas.validar_dominio("painel.são-paulo.br", base).startswith("painel.xn--")
    for ruim in ("localhost", "x.hubcapture.com.br", "a b.com", "-x.com"):
        with pytest.raises(HTTPException):
            marcas.validar_dominio(ruim, base)


def test_comparar_dns() -> None:
    assert marcas.comparar_dns({"1.1.1.1"}, {"1.1.1.1", "2.2.2.2"})[0] is True
    ok, msg = marcas.comparar_dns({"1.1.1.1", "9.9.9.9"}, {"1.1.1.1"})
    assert ok is False and "9.9.9.9" in msg
    assert marcas.comparar_dns(set(), {"1.1.1.1"})[0] is False


def test_yaml_traefik_e_host_malicioso() -> None:
    y = dominios.yaml_traefik(
        "painel.x.gov.br", "http://web:3000", "letsencrypt", "web", "websecure"
    )
    assert 'rule: "Host(`painel.x.gov.br`)"' in y and "certResolver: letsencrypt" in y
    assert "redirectScheme" in y
    with pytest.raises(ValueError):
        dominios.yaml_traefik("x.com`) || Host(`y.com", "http://w", "le", "web", "websecure")


def test_svg_perde_o_que_executa() -> None:
    sujo = (
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        b'<script>alert(2)</script><a href="javascript:alert(3)"><rect/></a>'
        b"<foreignObject><div>x</div></foreignObject></svg>"
    )
    limpo = marcas.sanitizar_svg(sujo).decode()
    assert "script" not in limpo and "onload" not in limpo
    assert "javascript:" not in limpo and "foreignObject" not in limpo
    assert "<rect/>" in limpo


# ── Identidade em e-mail, PDF, push e Copiloto ──────────────────────────────

_MARCA = identidade.Identidade(
    nome="Gabinete Digital",
    assistente="Assistente GD",
    acento="#ff5500",
    escuro="#101030",
    acao="#123456",
    url_base="https://gd.hubcapture.com.br",
    padrao=False,
)


def test_email_sem_marca_continua_hub_capture() -> None:
    assunto, _txt, html = email_templates.convite("http://x", None)
    assert assunto == "Seu convite para o Hub Capture"
    assert "Hub&nbsp;Capture" in html


def test_email_com_marca_troca_nome_cor_e_logo() -> None:
    with identidade.usar(_MARCA):
        assunto, txt, html = email_templates.redefinir_senha("https://gd/reset")
    assert assunto.endswith("Gabinete Digital")
    assert "#101030" in html and "Hub Capture" not in html and "Hub Capture" not in txt
    logo = identidade.Identidade(**{**_MARCA.__dict__, "logo_url": "https://gd/logo.png"})
    with identidade.usar(logo):
        _a, _t, html = email_templates.boas_vindas("Ana")
    assert "<img src='https://gd/logo.png'" in html


def test_remetente_ganha_o_nome_da_marca() -> None:
    from src.notifications import email

    with identidade.usar(_MARCA):
        assert email._remetente_da_marca("Hub <no-reply@hub.com>") == (
            '"Gabinete Digital" <no-reply@hub.com>'
        )
    assert email._remetente_da_marca("Hub <a@b.c>") == "Hub <a@b.c>"


def test_pdf_com_marca_e_logo() -> None:
    from src.models.proposta import Proposta

    p = Proposta(
        fonte="transferegov_disc",
        id_externo="1",
        titulo="UBS",
        municipio_ibge="3550308",
        municipio_nome="São Paulo",
        uf="SP",
    )
    com_logo = identidade.Identidade(**{**_MARCA.__dict__, "logo_bytes": PNG})
    with identidade.usar(com_logo):
        conteudo = pdf.gerar_pdf_proposta(p)
    assert conteudo.startswith(b"%PDF")
    assert b"Gabinete Digital" in conteudo  # metadado author/creator


def test_push_e_copiloto_assinam_pela_marca() -> None:
    from src.models.alerta import Alerta

    a = Alerta(usuario_id=uuid.uuid4(), tipo="situacao", payload={})
    with identidade.usar(_MARCA):
        assert oportunidades.mensagem_push([a])["title"].startswith("Gabinete Digital ·")
        assert "Assistente GD do Gabinete Digital" in agent.system_prompt("executivo")
    assert "Copiloto do Hub Capture" in agent.system_prompt("executivo")


# ── Ponta a ponta (API) ─────────────────────────────────────────────────────


async def _usuario(uid: uuid.UUID) -> Usuario:
    async with SessionLocal() as s:
        return await s.get(Usuario, uid)


async def _promover(uid: uuid.UUID) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(text("UPDATE usuarios SET is_superuser=true WHERE id=:id"), {"id": uid})


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _como(uid: uuid.UUID) -> None:
    u = await _usuario(uid)
    app.dependency_overrides[current_active_user] = lambda: u
    if u.is_superuser:
        app.dependency_overrides[current_superuser] = lambda: u


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


async def _criar_marca(c: httpx.AsyncClient, **kw) -> dict:
    corpo = {"slug": "gabinete", "nome": "Gabinete Digital", **kw}
    r = await c.post("/api/v1/admin/brands", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


async def test_admin_cria_marca_e_o_host_veste_o_site(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    dono = await seed_user("dono@gd.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c, dono_email="dono@gd.com", tema={"cores": {"acento": "#ff5500"}})
        assert m["host_padrao"] == "gabinete.hubcapture.com.br"
        assert m["dono_email"] == "dono@gd.com"
        # provisionamento padrão é manual: registra o host e diz o que falta
        assert m["provisionamento"][0]["status"] == "manual"

        r = await c.get(
            "/api/v1/branding", headers={"X-Forwarded-Host": "gabinete.hubcapture.com.br"}
        )
        b = r.json()
        assert b["personalizada"] is True and b["nome"] == "Gabinete Digital"
        assert "--color-accent:#ff5500" in b["css"]

        # host da plataforma e host desconhecido seguem Hub Capture
        for host in (
            "hubcapture.com.br",
            "www.hubcapture.com.br",
            "outro.com",
            "x.y.hubcapture.com.br",
        ):
            r = await c.get("/api/v1/branding", params={"host": host})
            assert r.json()["personalizada"] is False, host

        # marca desativada some do host
        r = await c.patch(f"/api/v1/brands/{m['id']}", json={"ativo": False})
        assert r.status_code == 200
        r = await c.get("/api/v1/branding", params={"host": "gabinete.hubcapture.com.br"})
        assert r.json()["personalizada"] is False

    # o dono passou a assinar pela marca
    assert (await _usuario(dono)).marca_id == uuid.UUID(m["id"])


async def test_dono_edita_tema_mas_nao_campos_de_admin(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    dono = await seed_user("dono@gd.com")
    intruso = await seed_user("x@y.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c, dono_email="dono@gd.com")
    app.dependency_overrides.clear()

    await _como(dono)
    async with _cliente() as c:
        r = await c.get("/api/v1/brands/mine")
        assert [x["slug"] for x in r.json()] == ["gabinete"]
        r = await c.patch(
            f"/api/v1/brands/{m['id']}",
            json={"tema": {"forma": "arredondada", "login_titulo": "Bem-vindo  ao  GD"}},
        )
        assert r.status_code == 200
        assert r.json()["tema"]["forma"] == "arredondada"
        assert r.json()["tema"]["login_titulo"] == "Bem-vindo ao GD"
        r = await c.patch(f"/api/v1/brands/{m['id']}", json={"slug": "outro"})
        assert r.status_code == 403
        r = await c.patch(f"/api/v1/brands/{m['id']}", json={"tema": {"cores": {"acento": "x"}}})
        assert r.status_code == 422

    await _como(intruso)
    async with _cliente() as c:
        assert (await c.get(f"/api/v1/brands/{m['id']}")).status_code == 404


async def test_upload_de_logo_valida_pelos_bytes(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c)
        r = await c.put(
            f"/api/v1/brands/{m['id']}/assets/logo",
            files={"arquivo": ("logo.png", PNG, "image/png")},
        )
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        r = await c.get(url)
        assert r.status_code == 200 and r.content == PNG
        assert "immutable" in r.headers["cache-control"]
        assert "sandbox" in r.headers["content-security-policy"]
        # HTML com extensão .png é recusado
        r = await c.put(
            f"/api/v1/brands/{m['id']}/assets/logo",
            files={"arquivo": ("logo.png", b"<html><script>x</script>", "image/png")},
        )
        assert r.status_code == 415
        # fonte só aceita woff2
        r = await c.put(
            f"/api/v1/brands/{m['id']}/assets/fonte_corpo",
            files={"arquivo": ("f.woff2", PNG, "font/woff2")},
        )
        assert r.status_code == 415
        r = await c.get("/api/v1/branding", params={"host": "gabinete.hubcapture.com.br"})
        assert r.json()["logo_url"] == url


async def test_dominio_proprio_verifica_dns_e_provisiona(
    seed_user, monkeypatch, tmp_path: Path
) -> None:
    admin = await seed_user("admin@hub.com")
    await _promover(admin)
    await _como(admin)

    ips = {"painel.prefeitura.gov.br": {"10.0.0.1"}, "gabinete.hubcapture.com.br": {"10.0.0.1"}}

    async def _resolver(host: str) -> set[str]:
        return ips.get(host, set())

    monkeypatch.setattr(marcas, "resolver_ips", _resolver)
    async with SessionLocal() as s, s.begin():
        await config_service.definir(s, "whitelabel_provisionador", "traefik_arquivo")
        await config_service.definir(s, "whitelabel_traefik_dir", str(tmp_path))

    async with _cliente() as c:
        m = await _criar_marca(c)
        # o subdomínio também ganhou rota
        assert (tmp_path / "hubcapture-wl-gabinete-hubcapture-com-br.yml").exists()

        r = await c.put(
            f"/api/v1/brands/{m['id']}/domain", json={"dominio": "Painel.Prefeitura.gov.br"}
        )
        assert r.json()["dominio"] == "painel.prefeitura.gov.br"
        assert r.json()["dominio_status"] == "pendente"
        # pendente ainda não responde pelo host
        r = await c.get("/api/v1/branding", params={"host": "painel.prefeitura.gov.br"})
        assert r.json()["personalizada"] is False

        # DNS apontando para outro lugar → erro com o motivo
        ips["painel.prefeitura.gov.br"] = {"8.8.8.8"}
        r = await c.post(f"/api/v1/brands/{m['id']}/domain/verify")
        assert r.json()["dominio_status"] == "erro" and "8.8.8.8" in r.json()["dominio_detalhe"]

        ips["painel.prefeitura.gov.br"] = {"10.0.0.1"}
        r = await c.post(f"/api/v1/brands/{m['id']}/domain/verify")
        assert r.json()["dominio_status"] == "ativo", r.json()
        assert r.json()["url"] == "https://painel.prefeitura.gov.br"
        arq = tmp_path / "hubcapture-wl-painel-prefeitura-gov-br.yml"
        assert "Host(`painel.prefeitura.gov.br`)" in arq.read_text()
        r = await c.get("/api/v1/branding", params={"host": "painel.prefeitura.gov.br"})
        assert r.json()["personalizada"] is True

        # trocar o domínio remove a rota antiga
        r = await c.put(f"/api/v1/brands/{m['id']}/domain", json={"dominio": None})
        assert r.json()["dominio"] is None and not arq.exists()


async def test_dominio_manual_fica_verificado_ate_o_admin_ativar(seed_user, monkeypatch) -> None:
    admin = await seed_user("admin@hub.com")
    await _promover(admin)
    await _como(admin)

    async def _resolver(_host: str) -> set[str]:
        return {"10.0.0.1"}

    monkeypatch.setattr(marcas, "resolver_ips", _resolver)
    async with _cliente() as c:
        m = await _criar_marca(c)
        await c.put(f"/api/v1/brands/{m['id']}/domain", json={"dominio": "gd.org.br"})
        r = await c.post(f"/api/v1/brands/{m['id']}/domain/verify")
        assert r.json()["dominio_status"] == "verificado"
        assert "Aguardando ativação" in r.json()["dominio_detalhe"]
        r = await c.post(f"/api/v1/admin/brands/{m['id']}/domain/activate")
        assert r.json()["dominio_status"] == "ativo"


async def test_cadastro_no_host_da_marca_entra_nela_com_o_plano(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    await _promover(admin)
    plano = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO planos (id, nome, slug, ativo) VALUES (:id,'Marca','marca',true)"),
            {"id": plano},
        )
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c, plano_id=str(plano))
    app.dependency_overrides.clear()

    async with _cliente() as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "novo@gd.com", "password": "segredo123", "nome": "Novo"},
            headers={"X-Forwarded-Host": "gabinete.hubcapture.com.br"},
        )
        assert r.status_code == 201, r.text
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "fora@x.com", "password": "segredo123"},
            headers={"X-Forwarded-Host": "hubcapture.com.br"},
        )
        assert r.status_code == 201

    async with SessionLocal() as s:
        novo = (await s.execute(select(Usuario).where(Usuario.email == "novo@gd.com"))).scalar_one()
        fora = (await s.execute(select(Usuario).where(Usuario.email == "fora@x.com"))).scalar_one()
    assert novo.marca_id == uuid.UUID(m["id"]) and novo.plano_id == plano
    assert fora.marca_id is None


async def test_cadastro_fechado_nao_vincula(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c)
        await c.patch(f"/api/v1/brands/{m['id']}", json={"cadastro_aberto": False})
    app.dependency_overrides.clear()
    async with _cliente() as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "novo@gd.com", "password": "segredo123"},
            headers={"X-Forwarded-Host": "gabinete.hubcapture.com.br"},
        )
    async with SessionLocal() as s:
        novo = (await s.execute(select(Usuario).where(Usuario.email == "novo@gd.com"))).scalar_one()
    assert novo.marca_id is None


async def test_convite_da_marca_vincula_quem_aceita(seed_user, monkeypatch) -> None:
    admin = await seed_user("admin@hub.com")
    dono = await seed_user("dono@gd.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c, dono_email="dono@gd.com")
    app.dependency_overrides.clear()

    enviados: list[tuple[str, str]] = []

    async def _enviar(dest, assunto, txt, html=None, **_kw):  # noqa: ANN001
        enviados.append((assunto, txt))
        return True

    monkeypatch.setattr("src.notifications.email.enviar", _enviar)
    await _como(dono)
    async with _cliente() as c:
        r = await c.post(f"/api/v1/brands/{m['id']}/invites", json={"email": "eq@gd.com"})
        assert r.status_code == 201, r.text
        token = r.json()["token"]
        r = await c.get(f"/api/v1/brands/{m['id']}/invites")
        assert len(r.json()) == 1
    app.dependency_overrides.clear()
    # o convite saiu assinado pela marca, com o link do host dela
    assert enviados and enviados[0][0] == "Seu convite para o Gabinete Digital"
    assert "https://gabinete.hubcapture.com.br/accept-invite" in enviados[0][1]

    async with _cliente() as c:
        r = await c.post(
            "/api/v1/auth/accept-invite",
            json={"token": token, "senha": "segredo123", "nome": "Equipe"},
        )
        assert r.status_code == 200, r.text
    async with SessionLocal() as s:
        eq = (await s.execute(select(Usuario).where(Usuario.email == "eq@gd.com"))).scalar_one()
        conv = (await s.execute(select(Convite))).scalar_one()
    assert eq.marca_id == uuid.UUID(m["id"]) and conv.marca_id == eq.marca_id

    await _como(dono)
    async with _cliente() as c:
        r = await c.get(f"/api/v1/brands/{m['id']}/members")
        assert {x["email"] for x in r.json()} == {"dono@gd.com", "eq@gd.com"}
        assert (await c.delete(f"/api/v1/brands/{m['id']}/members/{dono}")).status_code == 400
        assert (await c.delete(f"/api/v1/brands/{m['id']}/members/{eq.id}")).status_code == 204
    assert (await _usuario(eq.id)).marca_id is None


async def test_excluir_marca_nao_exclui_contas(seed_user) -> None:
    admin = await seed_user("admin@hub.com")
    dono = await seed_user("dono@gd.com")
    await _promover(admin)
    await _como(admin)
    async with _cliente() as c:
        m = await _criar_marca(c, dono_email="dono@gd.com")
        assert (await c.delete(f"/api/v1/admin/brands/{m['id']}")).status_code == 204
    u = await _usuario(dono)
    assert u is not None and u.marca_id is None


async def test_preview_escopado(seed_user) -> None:
    uid = await seed_user("a@b.com")
    await _como(uid)
    async with _cliente() as c:
        r = await c.post(
            "/api/v1/branding/preview",
            json={"tema": {"cores": {"acao": "#a0f0d0"}, "fonte_corpo": "lato"}},
        )
    j = r.json()
    assert ".marca-preview{" in j["css"] and j["fontes_urls"] and j["avisos"]
