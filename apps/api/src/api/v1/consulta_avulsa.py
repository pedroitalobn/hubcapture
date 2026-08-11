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
from ...schemas.proposta import PropostaRead, PropostasFacetas
from ...services import consulta_avulsa as service
from ...services import propostas as propostas_service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Faz parte do eixo de captação — segue o mesmo módulo de `proposals`.
router = APIRouter(tags=["proposals"], dependencies=[Depends(require_modulo("captacao"))])


class LiveSearchRequest(BaseModel):
    """Filtros da busca. Tudo opcional — sem município, usa os do perfil."""

    # Recorte do painel: quais dos municípios do perfil o usuário quer ver
    # agora. Lista vazia/ausente = todos os do território.
    municipios_ibge: list[str] | None = Field(
        default=None, description="códigos IBGE (7 dígitos) do recorte escolhido no painel"
    )
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    fonte: str | None = None
    area: str | None = None
    situacao: str | None = None
    modalidade: str | None = Field(default=None, description="tipo de instrumento")
    orgao: str | None = Field(default=None, description="órgão/ministério concedente")
    natureza_juridica: str | None = Field(
        default=None, description="municipal | estadual_df | consorcio | empresa_publica | osc"
    )
    qualificacao: str | None = Field(default=None, description="tipo de transferência")
    categoria: str | None = Field(
        default=None, description="pílula de categoria (saude, infraestrutura, cultura…)"
    )
    ano: str | None = Field(default=None, max_length=4)
    mes: str | None = Field(default=None, pattern="^(0[1-9]|1[0-2])$")
    q: str | None = Field(default=None, description="busca por programa, órgão ou código")
    valor_min: Decimal | None = Field(default=None, ge=0)
    valor_max: Decimal | None = Field(default=None, ge=0)
    tipo: str | None = Field(default=None, pattern="^(cadastrada|disponivel)$")
    ordenar: str | None = Field(
        default=None, pattern="^(recentes|prazo|prazo_distante|nome|orgao|valor)$"
    )
    limite: int | None = Field(
        default=None, ge=1, le=200, description="itens da página devolvida (sem limite: tudo)"
    )
    offset: int = Field(default=0, ge=0)


class FonteStatus(BaseModel):
    fonte: str
    municipio_ibge: str
    # 'degradado' = a fonte respondeu, mas parte do retorno não era proposta e
    # foi descartada na triagem da ingestão (ver `ingestion/validador.py`)
    status: str  # 'ok' | 'degradado' | 'erro'
    erro: str | None = None


class LiveSearchResponse(BaseModel):
    propostas: list[PropostaRead]
    # total do recorte (a lista acima é só a página pedida em `limite`/`offset`)
    total: int
    fontes: list[FonteStatus]
    # opções dos dropdowns já do recorte recém-coletado (evita 2ª chamada)
    facetas: PropostasFacetas


@router.post("/proposals/live-search", response_model=LiveSearchResponse)
async def live_search_endpoint(
    body: LiveSearchRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> LiveSearchResponse:
    filtros = body.model_dump(exclude={"municipios_ibge"})
    rows, total, status_fontes = await service.live_search(
        session, usuario_id=user.id, municipio=body.municipios_ibge, **filtros
    )
    # mesmas dimensões da listagem, sem repetir a lista de filtros à mão (a
    # versão anterior esquecia toda dimensão nova até alguém notar na tela).
    # Paginação fora: a faceta conta o recorte INTEIRO, não a página.
    facetas = await propostas_service.facetas(
        session,
        municipio=body.municipios_ibge,
        **body.model_dump(exclude={"municipios_ibge", "ordenar", "limite", "offset"}),
    )
    return LiveSearchResponse(
        propostas=[PropostaRead.model_validate(r) for r in rows],
        total=total,
        fontes=[FonteStatus(**s) for s in status_fontes],
        facetas=PropostasFacetas.model_validate(facetas),
    )
