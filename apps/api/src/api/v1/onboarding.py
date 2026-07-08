"""Endpoint de onboarding (grava municípios/preferências + 1º sync opcional)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.curadoria import OnboardingRequest, OnboardingResponse
from ...services import onboarding as service
from ..deps import get_rls_db

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding", response_model=OnboardingResponse)
async def onboarding(
    body: OnboardingRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> OnboardingResponse:
    return await service.onboarding(session, usuario_id=user.id, req=body)
