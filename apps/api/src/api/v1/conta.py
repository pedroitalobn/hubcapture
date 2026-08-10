"""Membros da conta — o usuário convida a própria equipe (limite do plano).

Diferente de `/admin/invites` (staff da plataforma convidando CLIENTES), aqui
é o assinante chamando MEMBROS para a conta dele: o convite herda o plano do
convidante e nasce com papel "equipe". `membros_max` da config do plano (§39)
limita quantos convites vivos a conta pode ter — excedeu → 403
`LIMITE_PLANO_MEMBROS` (o front oferece upgrade). O aceite reusa o fluxo
público `/auth/accept-invite` de sempre.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.planos import MembroConviteCreate, MembroRead
from ...services import gestao_usuarios as service
from ...services.gestao_usuarios import LimiteMembrosExcedido
from ..deps import get_platform_db

router = APIRouter(tags=["conta"])


@router.get("/account/members", response_model=list[MembroRead])
async def listar_membros(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[MembroRead]:
    return await service.listar_membros(session, user.id)


@router.post(
    "/account/members/invites", response_model=MembroRead, status_code=status.HTTP_201_CREATED
)
async def convidar_membro(
    body: MembroConviteCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> MembroRead:
    try:
        convite = await service.convidar_membro(session, user, body)
    except LimiteMembrosExcedido as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"LIMITE_PLANO_MEMBROS: máximo de {exc.maximo} membro(s) no seu plano",
        ) from exc
    return MembroRead(
        convite_id=convite.id,
        email=convite.email,
        papel=convite.papel,
        status=convite.status,
        expires_at=convite.expires_at,
        created_at=convite.created_at,
    )


@router.delete("/account/members/invites/{convite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revogar_convite(
    convite_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    await service.revogar_convite_membro(session, user.id, convite_id)
