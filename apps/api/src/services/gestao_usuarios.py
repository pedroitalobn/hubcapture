"""Gestão de usuários: convites (criar/aceitar) e admin (criar/atribuir plano).

Criação de usuário passa pelo UserManager (fastapi-users) para o hash de senha e
os hooks. Planos/convites são platform-level (sem RLS); `usuarios` também.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.users import UserManager
from ..models.convite import Convite
from ..models.usuario import Usuario
from ..schemas.planos import (
    AceitarConvite,
    AdminUsuarioCreate,
    AdminUsuarioUpdate,
    ConviteCreate,
    MembroConviteCreate,
    MembroRead,
)
from ..schemas.user import UserCreate
from . import plano_gates


class LimiteMembrosExcedido(Exception):
    """Convites de membro além do limite do plano (config `membros_max`)."""

    def __init__(self, maximo: int) -> None:
        self.maximo = maximo
        super().__init__(f"limite de {maximo} membro(s) do plano excedido")


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
    # e-mail de convite (best-effort; desabilitado sem SMTP configurado)
    try:
        from ..core.config import settings
        from ..notifications import email as email_service
        from ..notifications import email_templates as templates
        from ..services import config as config_service

        base = (await config_service.resolver("app_base_url")) or settings.app_base_url
        url = f"{base}/accept-invite?token={convite.token}"
        assunto, txt, html = templates.convite(url, convite.papel)
        await email_service.enviar(convite.email, assunto, txt, html)
    except Exception:  # noqa: BLE001 — falha de e-mail não invalida o convite
        pass
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


# ── Membros da conta ────────────────────────────────────────────────────────
# O usuário (não-admin) convida gente para a PRÓPRIA conta/equipe. O membro
# entra com o MESMO plano do convidante (a conta é uma só) e papel "equipe"
# por padrão. `membros_max` da config do plano (§39) limita quantos convites
# vivos (pendentes + aceitos) a conta pode ter; 0 = não convida.


async def _convites_vivos(session: AsyncSession, usuario_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count(Convite.id)).where(
                Convite.convidado_por == usuario_id,
                Convite.status.in_(("pendente", "aceito")),
            )
        )
    ).scalar_one()


async def convidar_membro(
    session: AsyncSession, convidante: Usuario, dados: MembroConviteCreate
) -> Convite:
    if not convidante.is_superuser:
        cfg = await plano_gates.config_do_usuario(session, convidante.id)
        maximo = cfg.membros_max
        if maximo is not None and await _convites_vivos(session, convidante.id) >= maximo:
            raise LimiteMembrosExcedido(int(maximo))
    return await criar_convite(
        session,
        ConviteCreate(
            email=dados.email,
            papel=dados.papel or "equipe",
            plano_id=convidante.plano_id,
            expires_em_dias=dados.expires_em_dias,
        ),
        convidado_por=convidante.id,
    )


async def listar_membros(session: AsyncSession, usuario_id: uuid.UUID) -> list[MembroRead]:
    """Convites da conta + o usuário criado por cada convite aceito."""
    rows = (
        await session.execute(
            select(Convite, Usuario)
            .outerjoin(
                Usuario,
                (Usuario.email == Convite.email) & (Convite.status == "aceito"),
            )
            .where(Convite.convidado_por == usuario_id)
            .order_by(Convite.created_at.desc())
        )
    ).all()
    return [
        MembroRead(
            convite_id=c.id,
            email=c.email,
            papel=c.papel,
            status=c.status,
            expires_at=c.expires_at,
            created_at=c.created_at,
            usuario_id=u.id if u else None,
            nome=u.nome if u else None,
        )
        for c, u in rows
    ]


async def revogar_convite_membro(
    session: AsyncSession, usuario_id: uuid.UUID, convite_id: uuid.UUID
) -> None:
    """Revoga um convite PENDENTE da própria conta (aceito → remover o usuário
    é ação de admin; o convite fica como registro)."""
    convite = (
        await session.execute(
            select(Convite).where(Convite.id == convite_id, Convite.convidado_por == usuario_id)
        )
    ).scalar_one_or_none()
    if convite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CONVITE_NAO_ENCONTRADO")
    if convite.status != "pendente":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CONVITE_NAO_PENDENTE")
    await session.execute(delete(Convite).where(Convite.id == convite.id))


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
    # `safe=True` ignora is_superuser no input (segurança). Como aqui QUEM cria é
    # o admin, aplicamos plano/permissão explicitamente após a criação.
    valores: dict = {}
    if dados.plano_id:
        valores["plano_id"] = dados.plano_id
    if dados.is_superuser:
        valores["is_superuser"] = True
    if valores:
        await session.execute(update(Usuario).where(Usuario.id == user.id).values(**valores))
        for k, v in valores.items():
            setattr(user, k, v)  # reflete na resposta
        await session.flush()
    return user


async def listar_usuarios(session: AsyncSession) -> list[Usuario]:
    rows = await session.execute(select(Usuario).order_by(Usuario.created_at.desc()))
    return list(rows.scalars().all())


async def atualizar_usuario(
    session: AsyncSession, usuario_id: uuid.UUID, dados: AdminUsuarioUpdate
) -> Usuario:
    valores = dados.model_dump(exclude_unset=True)
    if valores:
        await session.execute(update(Usuario).where(Usuario.id == usuario_id).values(**valores))
    user = (
        await session.execute(select(Usuario).where(Usuario.id == usuario_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="usuário não encontrado")
    return user


async def atribuir_plano(
    session: AsyncSession, usuario_id: uuid.UUID, plano_id: uuid.UUID | None
) -> None:
    await session.execute(update(Usuario).where(Usuario.id == usuario_id).values(plano_id=plano_id))
