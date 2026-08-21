"""Planos + gestão de usuários (convites, criação admin, atribuição de plano)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi_users.db import SQLAlchemyUserDatabase
from pydantic import ValidationError
from sqlalchemy import select

from src.core.users import UserManager
from src.db.session import SessionLocal
from src.models.convite import Convite
from src.models.usuario import Usuario
from src.schemas.planos import (
    AceitarConvite,
    AdminUsuarioCreate,
    ConviteCreate,
    PlanoCreate,
    PlanoUpdate,
)
from src.services import gestao_usuarios as gestao
from src.services import planos as planos_service


def _user_manager(session) -> UserManager:
    return UserManager(SQLAlchemyUserDatabase(session, Usuario))


async def test_planos_crud_e_listagem_ativos() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            free = await planos_service.criar(
                s, PlanoCreate(nome="Free", slug="free", preco_mensal=Decimal("0"))
            )
            pro = await planos_service.criar(
                s,
                PlanoCreate(nome="Pro", slug="pro", preco_mensal=Decimal("99"), ativo=True),
            )
            await planos_service.atualizar(s, free, PlanoUpdate(ativo=False))
        async with s.begin():
            ativos = await planos_service.listar(s, apenas_ativos=True)
            assert {p.slug for p in ativos} == {"pro"}
            todos = await planos_service.listar(s, apenas_ativos=False)
            assert {p.slug for p in todos} == {"free", "pro"}
            assert pro.preco_mensal == Decimal("99")


async def test_admin_cria_usuario_com_plano() -> None:
    async with SessionLocal() as s:
        um = _user_manager(s)
        async with s.begin():
            plano = await planos_service.criar(s, PlanoCreate(nome="Pro", slug="pro"))
        plano_id = plano.id
        user = await gestao.criar_usuario(
            s,
            um,
            AdminUsuarioCreate(
                email="novo@ente.gov", senha="segredo123", papel="executivo", plano_id=plano_id
            ),
        )
        await s.commit()
        u = (await s.execute(select(Usuario).where(Usuario.id == user.id))).scalar_one()
        assert u.plano_id == plano_id
        assert u.papel == "executivo"


async def test_admin_cria_usuario_sem_papel_do_select_vazio() -> None:
    """O form do painel manda papel="" com "— sem papel —" selecionado. Isso
    violava o CHECK ck_usuarios_papel (500 mudo — "ao criar nada acontece");
    o schema agora normaliza vazio → None e a criação passa."""
    dados = AdminUsuarioCreate(email="sempapel@ente.gov", senha="segredo123", papel="")
    assert dados.papel is None
    async with SessionLocal() as s:
        user = await gestao.criar_usuario(s, _user_manager(s), dados)
        await s.commit()
        u = (await s.execute(select(Usuario).where(Usuario.id == user.id))).scalar_one()
        assert u.papel is None


def test_admin_usuario_papel_invalido_e_422() -> None:
    """Papel fora do catálogo é erro de VALIDAÇÃO (422), nunca CheckViolation."""
    with pytest.raises(ValidationError):
        AdminUsuarioCreate(email="x@ente.gov", senha="segredo123", papel="gestor")


async def test_admin_cria_usuario_email_duplicado_e_400() -> None:
    """E-mail repetido virava UserAlreadyExists sem tratamento (500). O serviço
    devolve 400 EMAIL_JA_CADASTRADO — o form mostra a causa."""
    dados = AdminUsuarioCreate(email="dup@ente.gov", senha="segredo123", papel="executivo")
    async with SessionLocal() as s:
        await gestao.criar_usuario(s, _user_manager(s), dados)
        await s.commit()
    async with SessionLocal() as s:
        with pytest.raises(HTTPException) as exc:
            await gestao.criar_usuario(s, _user_manager(s), dados)
        assert exc.value.status_code == 400
        assert exc.value.detail == "EMAIL_JA_CADASTRADO"


async def test_convite_criar_e_aceitar() -> None:
    async with SessionLocal() as s:
        um = _user_manager(s)
        async with s.begin():
            plano = await planos_service.criar(s, PlanoCreate(nome="Pro", slug="pro"))
            convite = await gestao.criar_convite(
                s,
                ConviteCreate(email="convidado@ente.gov", papel="equipe", plano_id=plano.id),
                convidado_por=None,
            )
            token = convite.token
        plano_id = plano.id
        user = await gestao.aceitar_convite(
            s, um, AceitarConvite(token=token, senha="segredo123", nome="Convidado")
        )
        await s.commit()
        u = (await s.execute(select(Usuario).where(Usuario.id == user.id))).scalar_one()
        assert u.email == "convidado@ente.gov"
        assert u.papel == "equipe"
        assert u.plano_id == plano_id
        conv = (await s.execute(select(Convite).where(Convite.token == token))).scalar_one()
        assert conv.status == "aceito"


async def test_convite_expirado_recusado() -> None:
    async with SessionLocal() as s:
        um = _user_manager(s)
        async with s.begin():
            convite = await gestao.criar_convite(
                s,
                ConviteCreate(email="tarde@ente.gov", expires_em_dias=-1),
                convidado_por=None,
            )
            token = convite.token
            assert convite.expires_at < datetime.now(UTC)
        with pytest.raises(HTTPException) as exc:
            await gestao.aceitar_convite(s, um, AceitarConvite(token=token, senha="segredo123"))
        assert exc.value.status_code == 410
