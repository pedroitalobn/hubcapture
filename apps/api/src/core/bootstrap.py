"""Bootstrap do superadmin inicial (roda no startup da API).

Se `ADMIN_EMAIL` + `ADMIN_PASSWORD` estão no ambiente, garante que existe um
superusuário com esse e-mail — criando-o (via UserManager, senha hasheada) ou
promovendo um usuário já existente a superuser ativo/verificado. É idempotente:
subir o container de novo não duplica nem reseta a senha de quem já existe.

Isso destrava o primeiro login no painel admin sem precisar de seed manual.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update

from ..db.session import SessionLocal
from ..db.user_db import get_user_db
from ..models.usuario import Usuario
from ..schemas.user import UserCreate
from .config import settings
from .users import UserManager

logger = logging.getLogger("hubcapture.bootstrap")


async def ensure_admin() -> None:
    email = (settings.admin_email or "").strip().lower()
    senha = settings.admin_password or ""
    if not email or not senha:
        return  # bootstrap desligado

    async with SessionLocal() as session:
        existente = (
            await session.execute(select(Usuario).where(Usuario.email == email))
        ).scalar_one_or_none()

        if existente is not None:
            # já existe → só garante que é superuser ativo/verificado
            if not (existente.is_superuser and existente.is_active):
                await session.execute(
                    update(Usuario)
                    .where(Usuario.id == existente.id)
                    .values(is_superuser=True, is_active=True, is_verified=True)
                )
                await session.commit()
                logger.info("admin promovido a superuser: %s", email)
            return

        # não existe → cria via UserManager (hash de senha + hook de preferências)
        user_db_gen = get_user_db(session)
        user_db = await user_db_gen.__anext__()
        manager = UserManager(user_db)
        user = await manager.create(
            UserCreate(email=email, password=senha, nome="Administrador", papel="equipe"),
            safe=True,
        )
        await session.execute(
            update(Usuario)
            .where(Usuario.id == user.id)
            .values(is_superuser=True, is_active=True, is_verified=True)
        )
        await session.commit()
        logger.info("superadmin criado: %s", email)
