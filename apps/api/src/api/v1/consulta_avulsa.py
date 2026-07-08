"""Endpoint de consulta-avulsa (fetch on-demand no cache miss/stale)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors.transferegov_ff import ConnectorClientError
from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.proposta import PropostaRead
from ...services import consulta_avulsa as service
from ..deps import get_rls_db

router = APIRouter(tags=["consulta-avulsa"])


class ConsultaAvulsaRequest(BaseModel):
    municipio_ibge: str = Field(min_length=7, max_length=7, description="código IBGE")
    fonte: str = "transferegov_ff"


@router.post("/consulta-avulsa", response_model=list[PropostaRead])
async def consulta_avulsa_endpoint(
    body: ConsultaAvulsaRequest,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[PropostaRead]:
    try:
        rows = await service.consulta_avulsa(
            session,
            usuario_id=user.id,
            municipio_ibge=body.municipio_ibge,
            fonte=body.fonte,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"FONTE_DESCONHECIDA: {body.fonte}",
        ) from exc
    except ConnectorClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except Exception as exc:  # fonte instável/indisponível
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FONTE_INDISPONIVEL: {type(exc).__name__}",
        ) from exc
    return [PropostaRead.model_validate(r) for r in rows]
