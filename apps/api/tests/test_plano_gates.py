"""Gates de features por plano (§39): normalização da config, guard de módulo,
recorte de fontes, limite de membros e reflexo no perfil."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import text, update

from src.core.users import UserManager
from src.db.session import SessionLocal, rls_session
from src.models.usuario import Usuario
from src.schemas.curadoria import MunicipioIn, OnboardingRequest
from src.schemas.planos import MembroConviteCreate, PlanoCreate, PlanoLimites
from src.services import gestao_usuarios as gestao
from src.services import onboarding as onboarding_service
from src.services import perfil as perfil_service
from src.services import plano_gates
from src.services import planos as planos_service
from src.services.modulos import require_modulo


class _FakeUser:
    def __init__(self, uid, papel: str = "executivo") -> None:
        self.id = uid
        self.papel = papel
        self.nome = None
        self.is_superuser = False


async def _criar_plano(limites: dict, slug: str = "plano-teste") -> uuid.UUID:
    async with SessionLocal() as s:
        async with s.begin():
            plano = await planos_service.criar(
                s,
                PlanoCreate(
                    nome=slug.title(), slug=slug, limites=PlanoLimites.model_validate(limites)
                ),
            )
            plano_id = plano.id
    return plano_id


async def _atribuir_plano(usuario_id: uuid.UUID, plano_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await s.execute(
                update(Usuario).where(Usuario.id == usuario_id).values(plano_id=plano_id)
            )
    plano_gates.limpar_cache()


# ── Normalização da config ──────────────────────────────────────────────────
def test_normalizar_formato_canonico() -> None:
    cfg = plano_gates.normalizar(
        {
            "municipios_max": 3,
            "membros_max": 1,
            "modulos": ["captacao", "copiloto"],
            "fontes": ["transferegov"],
            "features": {"export_pdf": False},
        }
    )
    assert cfg.municipios_max == 3 and cfg.membros_max == 1
    assert cfg.modulos == {"captacao", "copiloto"}
    # grupo expande para os connector ids da família
    assert "transferegov_ff" in cfg.fontes and "serpro" in cfg.fontes
    assert not plano_gates.fonte_liberada(cfg, "fns")
    assert plano_gates.grupos_liberados(cfg) == {"transferegov"}
    assert not plano_gates.feature_liberada(cfg, "export_pdf")
    # feature ausente = liberada (gate é opt-in)
    assert plano_gates.feature_liberada(cfg, "relatorio_csv")


def test_normalizar_formato_legado() -> None:
    """Seeds antigos: municipios + bool de módulo no topo continuam valendo."""
    cfg = plano_gates.normalizar({"municipios": 5, "alertas": True, "copiloto": False})
    assert cfg.municipios_max == 5
    assert not plano_gates.modulo_liberado(cfg, "copiloto")
    assert plano_gates.modulo_liberado(cfg, "captacao")
    assert plano_gates.modulo_liberado(cfg, "alertas")


def test_normalizar_sem_config_nao_restringe() -> None:
    cfg = plano_gates.normalizar(None)
    assert plano_gates.modulo_liberado(cfg, "copiloto")
    assert plano_gates.fonte_liberada(cfg, "fns")
    assert plano_gates.grupos_liberados(cfg) is None
    assert cfg.municipios_max is None and cfg.membros_max is None


def test_limites_tipados_rejeitam_chave_desconhecida() -> None:
    with pytest.raises(ValueError, match="módulos desconhecidos"):
        PlanoLimites.model_validate({"modulos": ["captacao", "inexistente"]})
    with pytest.raises(ValueError, match="fontes desconhecidas"):
        PlanoLimites.model_validate({"fontes": ["nasa"]})
    # como_jsonb não persiste os None (chave ausente = sem restrição)
    assert PlanoLimites.model_validate({"municipios_max": 2}).como_jsonb() == {"municipios_max": 2}


# ── Guard de módulo por plano ───────────────────────────────────────────────
async def test_require_modulo_403_quando_fora_do_plano(seed_user) -> None:
    uid = await seed_user("gate@a.com")
    plano_id = await _criar_plano({"modulos": ["captacao"]})
    await _atribuir_plano(uid, plano_id)

    async with SessionLocal() as s:
        user = await s.get(Usuario, uid)
        dep = require_modulo("copiloto")
        with pytest.raises(HTTPException) as exc:
            await dep(user)
        assert exc.value.status_code == 403
        assert "MODULO_NAO_INCLUIDO_PLANO" in exc.value.detail
        # módulo incluído no plano passa
        await require_modulo("captacao")(user)


async def test_require_modulo_superuser_nao_e_limitado(seed_user) -> None:
    uid = await seed_user("root@a.com")
    plano_id = await _criar_plano({"modulos": ["captacao"]}, slug="restrito")
    await _atribuir_plano(uid, plano_id)
    async with SessionLocal() as s:
        async with s.begin():
            await s.execute(update(Usuario).where(Usuario.id == uid).values(is_superuser=True))
        user = await s.get(Usuario, uid)
        await require_modulo("copiloto")(user)  # não levanta


# ── Perfil: plataforma ∩ plano ──────────────────────────────────────────────
async def test_perfil_intersecta_modulos_do_plano(seed_user, seed_municipio) -> None:
    uid = await seed_user("perfil@a.com")
    await seed_municipio(uid, "3550308")
    plano_id = await _criar_plano(
        {
            "municipios_max": 2,
            "membros_max": 1,
            "modulos": ["captacao", "obras"],  # obras está DESLIGADA na plataforma
            "fontes": ["transferegov"],
        }
    )
    await _atribuir_plano(uid, plano_id)

    async with rls_session(uid) as s:
        p = await perfil_service.get_perfil(s, _FakeUser(uid))
    # plataforma ∩ plano: captacao (obras segue off na plataforma) + os módulos
    # que nenhum plano recorta (plano_gates.SEMPRE_INCLUSOS)
    assert set(p.modulos) == {"captacao", "oportunidades", "regularidade"}
    assert p.plano is not None
    assert p.plano.municipios_max == 2 and p.plano.membros_max == 1
    assert p.plano.fontes == ["transferegov"]
    assert p.plano.features["export_pdf"] is True  # ausente = liberada


# ── Onboarding: municípios e fontes pelo plano ──────────────────────────────
async def test_onboarding_respeita_municipios_e_fontes_do_plano(seed_user) -> None:
    uid = await seed_user("onb@a.com")
    plano_id = await _criar_plano({"municipios_max": 1, "fontes": ["transferegov"]})
    await _atribuir_plano(uid, plano_id)

    req = OnboardingRequest(
        municipios=[
            MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP"),
            MunicipioIn(ibge="2611606", nome="Recife", uf="PE"),
        ],
        fontes=["transferegov", "fns"],
        areas=["saude"],
    )
    async with rls_session(uid) as s:
        with pytest.raises(onboarding_service.LimitePlanoExcedido):
            await onboarding_service.onboarding(s, usuario_id=uid, req=req)

    req_ok = OnboardingRequest(
        municipios=[MunicipioIn(ibge="3550308", nome="São Paulo", uf="SP")],
        fontes=["transferegov", "fns"],
        areas=["saude"],
    )
    async with rls_session(uid) as s:
        await onboarding_service.onboarding(s, usuario_id=uid, req=req_ok)
        await s.commit()
    # preferencias_usuario tem RLS por-tenant → leitura na sessão do usuário
    async with rls_session(uid) as s:
        fontes = (
            await s.execute(
                text("SELECT fontes FROM preferencias_usuario WHERE usuario_id = :u"),
                {"u": uid},
            )
        ).scalar_one()
    # fns foi escolhida mas está fora do plano → não entra nas preferências
    assert "fns" not in fontes and "transferegov_ff" in fontes


# ── Membros da conta ────────────────────────────────────────────────────────
async def test_convite_de_membro_respeita_membros_max(seed_user) -> None:
    uid = await seed_user("dono@a.com")
    plano_id = await _criar_plano({"membros_max": 1})
    await _atribuir_plano(uid, plano_id)

    async with SessionLocal() as s:
        dono = await s.get(Usuario, uid)
        async with s.begin_nested() if s.in_transaction() else s.begin():
            convite = await gestao.convidar_membro(s, dono, MembroConviteCreate(email="m1@a.com"))
        await s.commit()
        assert convite.papel == "equipe"
        assert convite.plano_id == plano_id  # membro herda o plano da conta

        with pytest.raises(gestao.LimiteMembrosExcedido):
            await gestao.convidar_membro(s, dono, MembroConviteCreate(email="m2@a.com"))

        membros = await gestao.listar_membros(s, uid)
        assert [m.email for m in membros] == ["m1@a.com"]
        assert membros[0].status == "pendente"

        # revogar o pendente libera a vaga
        await gestao.revogar_convite_membro(s, uid, membros[0].convite_id)
        await s.commit()
        await gestao.convidar_membro(s, dono, MembroConviteCreate(email="m3@a.com"))
        await s.commit()


async def test_membros_max_zero_bloqueia_convite(seed_user) -> None:
    uid = await seed_user("solo@a.com")
    plano_id = await _criar_plano({"membros_max": 0}, slug="solo")
    await _atribuir_plano(uid, plano_id)
    async with SessionLocal() as s:
        dono = await s.get(Usuario, uid)
        with pytest.raises(gestao.LimiteMembrosExcedido):
            await gestao.convidar_membro(s, dono, MembroConviteCreate(email="x@a.com"))


async def test_membro_aceito_aparece_na_lista(seed_user) -> None:
    uid = await seed_user("lider@a.com")
    plano_id = await _criar_plano({"membros_max": 5}, slug="equipe5")
    await _atribuir_plano(uid, plano_id)
    async with SessionLocal() as s:
        dono = await s.get(Usuario, uid)
        convite = await gestao.convidar_membro(s, dono, MembroConviteCreate(email="membro@a.com"))
        await s.commit()
        token = convite.token

        from src.schemas.planos import AceitarConvite

        um = UserManager(SQLAlchemyUserDatabase(s, Usuario))
        membro = await gestao.aceitar_convite(
            s, um, AceitarConvite(token=token, senha="segredo123", nome="Membro")
        )
        await s.commit()
        assert membro.plano_id == plano_id

        membros = await gestao.listar_membros(s, uid)
        assert membros[0].status == "aceito"
        assert membros[0].usuario_id == membro.id
