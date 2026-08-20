"""Endpoints de perfil — a navegação parte do usuário, não da fonte de dados.

`GET /perfil` devolve o território (municípios), áreas e papel; `GET /perfil/
visao-geral` agrega as 4 dimensões do ciclo já recortadas pelo perfil (RLS).
São a fonte de verdade da navegação profile-centric do web.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.perfil import (
    NovidadesPerfil,
    PerfilRead,
    RemocaoMunicipioResultado,
    ResetPerfilResultado,
    VisaoGeralPerfil,
)
from ...services import demo as demo_service
from ...services import perfil as service
from ..deps import get_rls_db

router = APIRouter(tags=["perfil"])


@router.get("/profile", response_model=PerfilRead)
async def get_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> PerfilRead:
    return await service.get_perfil(session, user)


@router.delete("/profile", response_model=ResetPerfilResultado)
async def zerar_perfil(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> ResetPerfilResultado:
    """Zona de perigo da conta: volta ao estado pré-onboarding.

    Apaga território, preferências e curadoria do PRÓPRIO usuário (o RLS não
    deixa alcançar outro tenant) e invalida o cache do território para a
    próxima coleta recomeçar do zero. A conta continua existindo — o usuário
    cai no onboarding de novo.
    """
    demo_service.bloquear_escrita(user)  # sandbox compartilhado: nunca zerar
    return await service.zerar(session, user)


@router.delete("/profile/municipalities/{ibge}", response_model=RemocaoMunicipioResultado)
async def remover_municipio(
    ibge: str,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> RemocaoMunicipioResultado:
    """Tira UM município do território, sem zerar o perfil.

    Remove a linha do território e as buscas monitoradas daquele município. O
    cache (propostas, repasses, obras) não é apagado: é global e compartilhado
    com outros clientes — sair do território já esconde tudo pelo RLS.
    """
    demo_service.bloquear_escrita(user)  # o território demo é o palco da venda
    try:
        return await service.remover_municipio(session, user, ibge)
    except service.MunicipioNaoEncontrado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MUNICIPIO_FORA_DO_TERRITORIO",
        ) from None


# O painel filtra QUAIS dos municípios do perfil o usuário quer ver agora —
# repetir o parâmetro seleciona vários; omitir vale o território inteiro.
_MUNICIPIO_QUERY = Query(
    default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
)

# O filtro de ano do Meu painel vale para a página inteira (cards, gráfico e
# feed): é a MESMA safra em todas as consultas, senão o painel mostra recortes
# diferentes lado a lado. Multi-seleção como o município: repetir o parâmetro
# soma safras (`?ano=2024&ano=2025`); omitir vale todos os anos.
_ANO_QUERY = Query(
    default=None,
    description="safra(s) do recorte — repita o parâmetro para várias; omitir = todos os anos",
)


@router.get("/profile/overview", response_model=VisaoGeralPerfil)
async def visao_geral_perfil(
    municipio: list[str] | None = _MUNICIPIO_QUERY,
    ano: list[str] | None = _ANO_QUERY,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> VisaoGeralPerfil:
    return await service.visao_geral(session, user, municipios_filtro=municipio, ano=ano)


@router.get("/profile/feed", response_model=NovidadesPerfil)
async def novidades_perfil(
    municipio: list[str] | None = _MUNICIPIO_QUERY,
    limite: int = Query(default=20, ge=1, le=200, description="tamanho da janela do feed"),
    ano: list[str] | None = _ANO_QUERY,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> NovidadesPerfil:
    """Feed 'últimas novidades' do território, recortado pelo perfil do usuário.

    `limite` controla a profundidade da janela e `ano`, a safra: o filtro entra
    ANTES da janela, então escolher um ano anterior traz os itens daquele ano —
    não só os que sobraram das novidades mais recentes.
    """
    return await service.novidades(
        session, user, limite=limite, municipios_filtro=municipio, ano=ano
    )
