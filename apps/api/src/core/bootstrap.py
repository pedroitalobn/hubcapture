"""Bootstrap do superadmin inicial (roda no startup da API).

Se `ADMIN_EMAIL` + `ADMIN_PASSWORD` estão no ambiente, garante que existe um
superusuário com esse e-mail — criando-o (via UserManager, senha hasheada) ou
promovendo um usuário já existente a superuser ativo/verificado. É idempotente:
subir o container de novo não duplica nem reseta a senha de quem já existe.

Isso destrava o primeiro login no painel admin sem precisar de seed manual.

Duas defesas contra o bootstrap "perder a vez" (sintoma: login funciona mas o
usuário não é superuser e o painel admin nega acesso):
- `ensure_admin` tem RETRY com backoff — banco ainda subindo no startup não
  engole mais a promoção silenciosamente;
- `promover_se_admin_env` roda a cada LOGIN: se o e-mail autenticado é o
  ADMIN_EMAIL do ambiente e a conta não é superuser, promove na hora
  (auto-reparo sem redeploy).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update

from ..db.session import SessionLocal
from ..db.user_db import get_user_db
from ..models.usuario import Usuario
from ..schemas.user import UserCreate
from .config import settings
from .users import UserManager

logger = logging.getLogger("hubcapture.bootstrap")


async def ensure_admin(tentativas: int = 10, intervalo: float = 2.0) -> None:
    """Cria/promove o superadmin com retry (banco pode estar subindo)."""
    email = (settings.admin_email or "").strip().lower()
    senha = settings.admin_password or ""
    if not email or not senha:
        return  # bootstrap desligado

    ultima_falha: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            await _ensure_admin_uma_vez(email, senha)
            return
        except Exception as exc:  # noqa: BLE001 — retry deliberado
            ultima_falha = exc
            logger.warning(
                "bootstrap do admin falhou (tentativa %d/%d): %s",
                tentativa,
                tentativas,
                exc,
            )
            await asyncio.sleep(intervalo)
    logger.error(
        "bootstrap do admin DESISTIU após %d tentativas — o login do ADMIN_EMAIL "
        "ainda promove a superuser (auto-reparo). Última falha: %r",
        tentativas,
        ultima_falha,
    )


async def promover_se_admin_env(user: Usuario) -> bool:
    """Auto-reparo no login: se `user` é o ADMIN_EMAIL do ambiente e ainda não é
    superuser, promove (ativo+verificado). Retorna True se promoveu."""
    email = (settings.admin_email or "").strip().lower()
    if not email or (user.email or "").lower() != email or user.is_superuser:
        return False
    async with SessionLocal() as session:
        await session.execute(
            update(Usuario)
            .where(Usuario.id == user.id)
            .values(is_superuser=True, is_active=True, is_verified=True)
        )
        await session.commit()
    user.is_superuser = True
    user.is_active = True
    user.is_verified = True
    logger.info("admin do ambiente promovido no login: %s", email)
    return True


async def _ensure_admin_uma_vez(email: str, senha: str) -> None:
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
