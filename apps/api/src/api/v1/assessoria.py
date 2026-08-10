"""Assessoria orçamentária — a aba onde o gestor fala com uma PESSOA.

Lista os contatos da assessoria com o link do WhatsApp pronto. A lista é
editada pelo painel admin (`/admin/advisory/contacts`) sem redeploy; o módulo
`assessoria` pode ser desligado pelo painel de módulos (§29).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.assessoria import ContatoAssessoriaRead
from ...services import assessoria as service
from ...services.modulos import require_modulo
from ..deps import get_platform_db

router = APIRouter(tags=["assessoria"], dependencies=[Depends(require_modulo("assessoria"))])


@router.get("/advisory/contacts", response_model=list[ContatoAssessoriaRead])
async def listar_contatos(
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoAssessoriaRead]:
    return [ContatoAssessoriaRead(**c) for c in await service.listar(session)]
