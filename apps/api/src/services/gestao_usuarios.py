"""Gestão de usuários: convites (criar/aceitar) e admin (criar/atribuir plano).

Criação de usuário passa pelo UserManager (fastapi-users) para o hash de senha e
os hooks. Planos/convites são platform-level (sem RLS); `usuarios` também.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.users import UserManager
from ..models.convite import Convite
from ..models.usuario import Usuario
from ..schemas.planos import AceitarConvite, AdminUsuarioCreate, ConviteCreate
from ..schemas.user import UserCreate


# ── Convites ────────────────────────────────────────────────────────────────
async def criar_convite(
    session: AsyncSession, dados: ConviteCreate, convidado_por: uuid.UUID
) -> Convite:
    convite = Convite(
        email=str(dados.email),
        token=secrets.token_urlsafe(32),
        papel=dados.papel,
        plano_id=dados.plano_id,
        convidado_por=convidado_por,
        status="pendente",
        expires_at=datetime.now(UTC) + timedelta(days=dados.expires_em_dias),
    )
    session.add(convite)
    await session.flush()
    return convite


async def listar_convites(session: AsyncSession) -> list[Convite]:
    result = await session.execute(select(Convite).order_by(Convite.created_at.desc()))
    return list(result.scalars().all())


async def aceitar_convite(
    session: AsyncSession, user_manager: UserManager, dados: AceitarConvite
) -> Usuario:
    convite = (
        await session.execute(select(Convite).where(Convite.token == dados.token))
    ).scalar_one_or_none()
    if convite is None or convite.status != "pendente":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CONVITE_INVALIDO")
    if convite.expires_at and convite.expires_at < datetime.now(UTC):
        convite.status = "expirado"
        raise HTTPException(status.HTTP_410_GONE, "CONVITE_EXPIRADO")

    user = await user_manager.create(
        UserCreate(
            email=convite.email,
            password=dados.senha,
            nome=dados.nome,
            papel=convite.papel,
        ),
        safe=True,
    )
    if convite.plano_id:
        await session.execute(
            update(Usuario).where(Usuario.id == user.id).values(plano_id=convite.plano_id)
        )
        user.plano_id = convite.plano_id  # reflete na resposta (objeto de outra sessão)
    convite.status = "aceito"
    await session.flush()
    return user


# ── Admin: criação direta + atribuição de plano ─────────────────────────────
async def criar_usuario(
    session: AsyncSession, user_manager: UserManager, dados: AdminUsuarioCreate
) -> Usuario:
    user = await user_manager.create(
        UserCreate(
            email=dados.email,
            password=dados.senha,
            nome=dados.nome,
            papel=dados.papel,
        ),
        safe=True,
    )
    if dados.plano_id:
        await session.execute(
            update(Usuario).where(Usuario.id == user.id).values(plano_id=dados.plano_id)
        )
        user.plano_id = dados.plano_id  # reflete na resposta
        await session.flush()
    return user


async def atribuir_plano(
    session: AsyncSession, usuario_id: uuid.UUID, plano_id: uuid.UUID | None
) -> None:
    await session.execute(
        update(Usuario).where(Usuario.id == usuario_id).values(plano_id=plano_id)
    )
