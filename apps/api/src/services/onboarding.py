"""Onboarding: grava municípios monitorados + preferências e dispara 1º sync.

O sync inicial é best-effort e roda em SAVEPOINT por município: uma falha de
fonte (comum — APIs oficiais instáveis) reverte só o savepoint e é registrada em
`sync_runs`, sem derrubar o onboarding.
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
from . import repasses as repasses_service

# fontes de recebidos que o onboarding pode sincronizar de cara
FONTES_RECEBIDOS = {"fpm", "emendas", "fns", "fnde"}


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

    sync_disparado = False
    if req.disparar_sync:
        fontes = sorted(set(req.fontes) & FONTES_RECEBIDOS) or ["fpm", "emendas"]
        for m in req.municipios:
            try:
                async with session.begin_nested():
                    await repasses_service.sync_municipio(
                        session,
                        usuario_id=usuario_id,
                        municipio_ibge=m.ibge,
                        fontes=fontes,
                    )
            except Exception:
                pass  # sync_runs já registrou; onboarding não falha
        sync_disparado = True

    return OnboardingResponse(
        municipios=len(req.municipios), sync_disparado=sync_disparado
    )
