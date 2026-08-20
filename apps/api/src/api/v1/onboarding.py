"""Endpoint de onboarding (grava municípios/preferências + 1º sync em background).

O perfil é gravado na transação do request; o 1º sync (dados REAIS de todas as
dimensões — captação/recebidos/conformidade/obras) é agendado via
`primeiro_sync.agendar` (asyncio.create_task — NUNCA BackgroundTasks, que
rodaria antes do commit da sessão e travaria o perfil; ver o módulo do serviço).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.curadoria import OnboardingRequest, OnboardingResponse
from ...services import demo as demo_service
from ...services import onboarding as service
from ...services import primeiro_sync
from ...services.onboarding import LimitePlanoExcedido
from ..deps import get_rls_db

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding", response_model=OnboardingResponse)
async def onboarding(
    body: OnboardingRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> OnboardingResponse:
    # conta demo: o território é semeado pela plataforma e compartilhado —
    # refazer o onboarding trocaria o palco da apresentação de todo mundo
    demo_service.bloquear_escrita(user)
    try:
        resp = await service.onboarding(session, usuario_id=user.id, req=body)
    except LimitePlanoExcedido as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"LIMITE_PLANO_MUNICIPIOS: máximo de {exc.maximo} município(s) no seu plano",
        ) from exc
    if body.disparar_sync and body.municipios:
        primeiro_sync.agendar(
            user.id,
            [m.ibge for m in body.municipios],
            list(body.fontes),
            list(body.areas),
        )
    return resp
