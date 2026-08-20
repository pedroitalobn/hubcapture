"""Endpoints de alertas (RLS por usuario_id)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.monitoramento import AlertaRead, CriterioAlertaRead
from ...services import alertas as service
from ...services import criterios_alerta as criterios_service
from ...services import oportunidades as oportunidades_service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

router = APIRouter(tags=["alertas"], dependencies=[Depends(require_modulo("alertas"))])


@router.post("/alerts/scan")
async def varredura_alertas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> dict:
    """Roda a detecção de novas propostas (buscas) + oportunidades e despacha
    por email/WhatsApp conforme os canais. Retorna quantos alertas foram criados."""
    criados = await oportunidades_service.varredura(session, user)
    return {"alertas_criados": criados}


@router.get("/alerts/criteria", response_model=list[CriterioAlertaRead])
async def catalogo_criterios(
    escopo: str | None = Query(
        default=None,
        description="proposta (monitorar uma proposta) | territorio (monitorar um município)",
    ),
    _: Usuario = Depends(current_active_user),
) -> list[CriterioAlertaRead]:
    """Catálogo dos critérios de alerta — é ele que alimenta o multi-select.

    Critério novo aparece na tela sem alteração no front (§53)."""
    if escopo is not None and escopo not in criterios_service.ESCOPOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"escopo inválido: {escopo}",
        )
    return [
        CriterioAlertaRead(
            chave=c.chave,
            rotulo=c.rotulo,
            descricao=c.descricao,
            escopo=c.escopo,
            padrao=c.padrao,
        )
        for c in criterios_service.catalogo(escopo)
    ]


@router.get("/alerts", response_model=list[AlertaRead])
async def listar_alertas(
    nao_lidos: bool = Query(default=False),
    municipio: list[str] | None = Query(
        default=None, description="códigos IBGE (repita o parâmetro para vários municípios)"
    ),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[AlertaRead]:
    rows = await service.listar(session, user.id, apenas_nao_lidos=nao_lidos, municipio=municipio)
    return [AlertaRead.model_validate(r) for r in rows]


@router.post("/alerts/{alerta_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_lido(
    alerta_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.marcar_lido(session, user.id, alerta_id)
