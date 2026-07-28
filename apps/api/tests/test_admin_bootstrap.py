"""Bootstrap do superadmin + gestão de usuários (roles/permissions) pelo admin."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from src.db.session import SessionLocal
from src.db.user_db import get_user_db
from src.models.usuario import Usuario
from src.schemas.planos import AdminUsuarioCreate, AdminUsuarioUpdate
from src.services import gestao_usuarios as service


async def _manager():
    session = SessionLocal()
    user_db_gen = get_user_db(session)
    user_db = await user_db_gen.__anext__()
    from src.core.users import UserManager

    return session, UserManager(user_db)


async def test_bootstrap_cria_e_promove(monkeypatch) -> None:
    from src.core import bootstrap
    from src.core.config import settings

    email = f"admin-{uuid.uuid4().hex[:8]}@hub.com"
    monkeypatch.setattr(settings, "admin_email", email)
    monkeypatch.setattr(settings, "admin_password", "supersenha123")

    await bootstrap.ensure_admin()  # cria
    await bootstrap.ensure_admin()  # idempotente (não duplica)

    async with SessionLocal() as s:
        rows = (await s.execute(select(Usuario).where(Usuario.email == email))).scalars().all()
    assert len(rows) == 1
    assert rows[0].is_superuser and rows[0].is_active


async def test_admin_cria_usuario_com_role_e_permissao() -> None:
    session, manager = await _manager()
    try:
        user = await service.criar_usuario(
            session,
            manager,
            AdminUsuarioCreate(
                email=f"u-{uuid.uuid4().hex[:8]}@x.com",
                senha="senhaforte1",
                nome="Fulano",
                papel="parlamentar",
                is_superuser=True,
            ),
        )
        assert user.papel == "parlamentar" and user.is_superuser is True
    finally:
        await session.close()


async def test_admin_atualiza_role_e_permissao() -> None:
    session, manager = await _manager()
    try:
        user = await service.criar_usuario(
            session,
            manager,
            AdminUsuarioCreate(
                email=f"u-{uuid.uuid4().hex[:8]}@y.com", senha="senhaforte1", papel="equipe"
            ),
        )
        atualizado = await service.atualizar_usuario(
            session,
            user.id,
            AdminUsuarioUpdate(papel="executivo", is_superuser=True, is_active=False),
        )
        assert atualizado.papel == "executivo"
        assert atualizado.is_superuser is True and atualizado.is_active is False
    finally:
        await session.close()


async def test_login_promove_admin_do_ambiente(monkeypatch, seed_user) -> None:
    """Auto-reparo: conta com o e-mail do ADMIN_EMAIL que não é superuser
    (bootstrap perdido) é promovida ao logar."""
    from src.core import bootstrap
    from src.core.config import settings

    email = f"resgate-{uuid.uuid4().hex[:8]}@hub.com"
    uid = await seed_user(email)
    monkeypatch.setattr(settings, "admin_email", email)
    monkeypatch.setattr(settings, "admin_password", "irrelevante")

    async with SessionLocal() as s:
        user = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert not user.is_superuser
        promovido = await bootstrap.promover_se_admin_env(user)
        assert promovido
        # segunda chamada é no-op
        assert not await bootstrap.promover_se_admin_env(user)

    async with SessionLocal() as s:
        atualizado = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert atualizado.is_superuser and atualizado.is_active and atualizado.is_verified


async def test_promover_ignora_email_diferente(monkeypatch, seed_user) -> None:
    from src.core import bootstrap
    from src.core.config import settings

    uid = await seed_user("naoadmin@hub.com")
    monkeypatch.setattr(settings, "admin_email", "outro@hub.com")

    async with SessionLocal() as s:
        user = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert not await bootstrap.promover_se_admin_env(user)
        assert not user.is_superuser
