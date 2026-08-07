"""Endpoints de perfil — a navegação parte do usuário, não da fonte de dados.

`GET /perfil` devolve o território (municípios), áreas e papel; `GET /perfil/
visao-geral` agrega as 4 dimensões do ciclo já recortadas pelo perfil (RLS).
São a fonte de verdade da navegação profile-centric do web.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.perfil import NovidadesPerfil, PerfilRead, VisaoGeralPerfil
from ...services import perfil as service
from ..deps import get_rls_db

router = APIRouter(tags=["perfil"])


@router.get("/profile", response_model=PerfilRead)
async def get_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PerfilRead:
    return await service.get_perfil(session, user)


# O painel filtra QUAIS dos municípios do perfil o usuário quer ver agora —
# repetir o parâmetro seleciona vários; omitir vale o território inteiro.
_MUNICIPIO_QUERY = Query(
    default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
)


@router.get("/profile/overview", response_model=VisaoGeralPerfil)
async def visao_geral_perfil(
    municipio: list[str] | None = _MUNICIPIO_QUERY,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> VisaoGeralPerfil:
    return await service.visao_geral(session, user, municipios_filtro=municipio)


@router.get("/profile/feed", response_model=NovidadesPerfil)
async def novidades_perfil(
    municipio: list[str] | None = _MUNICIPIO_QUERY,
    limite: int = Query(default=20, ge=1, le=200, description="tamanho da janela do feed"),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> NovidadesPerfil:
    """Feed 'últimas novidades' do território, recortado pelo perfil do usuário.

    `limite` controla a profundidade da janela: o painel pede mais que o padrão
    para o filtro por ano alcançar itens de anos anteriores ao corrente.
    """
    return await service.novidades(session, user, limite=limite, municipios_filtro=municipio)
