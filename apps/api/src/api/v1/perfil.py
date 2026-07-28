"""Endpoints de perfil — a navegação parte do usuário, não da fonte de dados.

`GET /perfil` devolve o território (municípios), áreas e papel; `GET /perfil/
visao-geral` agrega as 4 dimensões do ciclo já recortadas pelo perfil (RLS).
São a fonte de verdade da navegação profile-centric do web.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.perfil import NovidadesPerfil, PerfilRead, VisaoGeralPerfil
from ...services import perfil as service
from ..deps import get_rls_db

router = APIRouter(tags=["perfil"])


@router.get("/perfil", response_model=PerfilRead)
async def get_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PerfilRead:
    return await service.get_perfil(session, user)


@router.get("/perfil/visao-geral", response_model=VisaoGeralPerfil)
async def visao_geral_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> VisaoGeralPerfil:
    return await service.visao_geral(session, user)


@router.get("/perfil/novidades", response_model=NovidadesPerfil)
async def novidades_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> NovidadesPerfil:
    """Feed 'últimas novidades' do território, recortado pelo perfil do usuário."""
    return await service.novidades(session, user)
