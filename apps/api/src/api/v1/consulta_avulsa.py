"""POST /proposals/live-search — busca em TEMPO REAL para a Captação.

Ao filtrar no painel, o front chama aqui: a API consulta ao vivo as fontes de
captação relevantes (API pública e/ou scraping, via connectors) para os
municípios do perfil — cache fresco responde na hora, stale/miss vai à fonte —
e devolve as propostas já filtradas + o status por fonte (best-effort: uma
fonte fora do ar não derruba a busca).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.proposta import PropostaRead
from ...services import consulta_avulsa as service
from ..deps import get_rls_db

router = APIRouter(tags=["proposals"])


class LiveSearchRequest(BaseModel):
    """Filtros da busca. Tudo opcional — sem município, usa os do perfil."""

    municipio_ibge: str | None = Field(
        default=None, min_length=7, max_length=7, description="código IBGE"
    )
    fonte: str | None = None
    area: str | None = None
    situacao: str | None = None
    valor_min: Decimal | None = Field(default=None, ge=0)
    valor_max: Decimal | None = Field(default=None, ge=0)
    tipo: str | None = Field(default=None, pattern="^(cadastrada|disponivel)$")


class FonteStatus(BaseModel):
    fonte: str
    municipio_ibge: str
    status: str  # 'ok' | 'erro'
    erro: str | None = None


class LiveSearchResponse(BaseModel):
    propostas: list[PropostaRead]
    fontes: list[FonteStatus]


@router.post("/proposals/live-search", response_model=LiveSearchResponse)
async def live_search_endpoint(
    body: LiveSearchRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> LiveSearchResponse:
    rows, status_fontes = await service.live_search(
        session,
        usuario_id=user.id,
        municipio=body.municipio_ibge,
        fonte=body.fonte,
        area=body.area,
        situacao=body.situacao,
        valor_min=body.valor_min,
        valor_max=body.valor_max,
        tipo=body.tipo,
    )
    return LiveSearchResponse(
        propostas=[PropostaRead.model_validate(r) for r in rows],
        fontes=[FonteStatus(**s) for s in status_fontes],
    )
