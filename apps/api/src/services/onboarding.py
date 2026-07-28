"""Onboarding: grava municípios monitorados + preferências do perfil.

O 1º sync (dados reais das fontes) NÃO roda aqui: o router agenda
`services.primeiro_sync.executar` como BackgroundTask — o onboarding responde
na hora e o painel se povoa conforme as fontes concluem (best-effort).
"""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.municipio_interesse import MunicipioInteresse
from ..models.preferencias import PreferenciasUsuario
from ..models.usuario import Usuario
from ..schemas.curadoria import OnboardingRequest, OnboardingResponse


async def onboarding(
    session: AsyncSession, *, usuario_id: uuid.UUID, req: OnboardingRequest
) -> OnboardingResponse:
    if req.papel:
        await session.execute(
            update(Usuario).where(Usuario.id == usuario_id).values(papel=req.papel)
        )

    for m in req.municipios:
        await session.execute(
            pg_insert(MunicipioInteresse)
            .values(
                usuario_id=usuario_id, ibge=m.ibge, nome=m.nome, uf=m.uf, modo="monitorado"
            )
            .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
        )

    prefs = pg_insert(PreferenciasUsuario).values(
        usuario_id=usuario_id,
        fontes=req.fontes,
        areas=req.areas,
        monitorar_ativo=req.monitorar_ativo,
    )
    prefs = prefs.on_conflict_do_update(
        index_elements=["usuario_id"],
        set_={
            "fontes": prefs.excluded.fontes,
            "areas": prefs.excluded.areas,
            "monitorar_ativo": prefs.excluded.monitorar_ativo,
        },
    )
    await session.execute(prefs)

    return OnboardingResponse(
        municipios=len(req.municipios), sync_disparado=req.disparar_sync
    )
