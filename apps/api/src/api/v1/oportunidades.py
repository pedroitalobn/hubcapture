"""Oportunidades — programas abertos em que o território pode se inscrever (§63)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.oportunidades import OportunidadesResposta
from ...services import programas as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

router = APIRouter(tags=["oportunidades"], dependencies=[Depends(require_modulo("oportunidades"))])


@router.get("/opportunities", response_model=OportunidadesResposta)
async def listar_oportunidades(
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    q: str | None = Query(default=None, description="nome, código ou órgão do programa"),
    orgao: str | None = Query(default=None, description="órgão superior concedente"),
    categoria: str | None = Query(default=None, description="slug de categoria (§32)"),
    janela: str | None = Query(default=None, description="voluntaria | emenda | beneficiario"),
    recomendados: bool = Query(default=False, description="só os que o perfil indica"),
    todas_naturezas: bool = Query(
        default=False,
        description="inclui programas que não aceitam ente municipal como proponente",
    ),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> OportunidadesResposta:
    dados = await service.listar(
        session,
        user.id,
        municipio=municipio,
        q=q,
        orgao=orgao,
        categoria=categoria,
        janela=janela if janela in service.JANELAS else None,
        apenas_recomendados=recomendados,
        incluir_outras_naturezas=todas_naturezas,
    )
    return OportunidadesResposta.model_validate(dados)
