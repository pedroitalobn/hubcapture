"""Onboarding: grava municípios monitorados + preferências do perfil.

O 1º sync (dados reais das fontes) NÃO roda aqui: o router agenda
`services.primeiro_sync.executar` como BackgroundTask — o onboarding responde
na hora e o painel se povoa conforme as fontes concluem (best-effort).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.municipio_interesse import MunicipioInteresse
from ..models.plano import Plano
from ..models.preferencias import PreferenciasUsuario
from ..models.usuario import Usuario
from ..schemas.curadoria import OnboardingRequest, OnboardingResponse
from . import fontes as fontes_service
from . import monitoramentos as monitoramentos_service


class LimitePlanoExcedido(Exception):
    """Municípios além do limite do plano (limites.municipios_max)."""

    def __init__(self, maximo: int) -> None:
        self.maximo = maximo
        super().__init__(f"limite de {maximo} município(s) do plano excedido")


async def _validar_limite_municipios(
    session: AsyncSession, usuario_id: uuid.UUID, req: OnboardingRequest
) -> None:
    """3 tiers × quantidade de municípios (fluxograma): o plano limita quantos
    municípios o usuário monitora. Sem plano/limite → ilimitado."""
    plano = (
        await session.execute(
            select(Plano)
            .join(Usuario, Usuario.plano_id == Plano.id)
            .where(Usuario.id == usuario_id)
        )
    ).scalar_one_or_none()
    maximo = (plano.limites or {}).get("municipios_max") if plano else None
    if not maximo:
        return
    existentes = set(
        (
            await session.execute(
                select(MunicipioInteresse.ibge).where(MunicipioInteresse.usuario_id == usuario_id)
            )
        )
        .scalars()
        .all()
    )
    total = len(existentes | {m.ibge for m in req.municipios})
    if total > int(maximo):
        raise LimitePlanoExcedido(int(maximo))


async def onboarding(
    session: AsyncSession, *, usuario_id: uuid.UUID, req: OnboardingRequest
) -> OnboardingResponse:
    await _validar_limite_municipios(session, usuario_id, req)

    valores_usuario: dict = {}
    if req.papel:
        valores_usuario["papel"] = req.papel
    if req.telefone_wpp is not None:
        valores_usuario["telefone_wpp"] = req.telefone_wpp or None
    if req.optin_wpp is not None:
        valores_usuario["optin_wpp"] = req.optin_wpp
    if valores_usuario:
        await session.execute(
            update(Usuario).where(Usuario.id == usuario_id).values(**valores_usuario)
        )

    for m in req.municipios:
        await session.execute(
            pg_insert(MunicipioInteresse)
            .values(usuario_id=usuario_id, ibge=m.ibge, nome=m.nome, uf=m.uf, modo="monitorado")
            .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
        )

    # O onboarding oferece GRUPOS ("transferegov", "fns"); o resto do sistema
    # fala connector id. A expansão acontece aqui, uma vez, na entrada — e
    # descarta fonte fora do recorte da v1 (`services/fontes.py`).
    fontes_escolhidas = fontes_service.expandir(req.fontes) or list(fontes_service.HABILITADAS)

    prefs = pg_insert(PreferenciasUsuario).values(
        usuario_id=usuario_id,
        fontes=fontes_escolhidas,
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

    # monitoramento de FUTURAS propostas: com monitorar_ativo, cada município
    # ganha uma busca ativa — novas propostas geram alerta nos canais escolhidos
    if req.monitorar_ativo:
        canais = list(req.canais_alerta or ["painel"])
        if req.optin_wpp and "wpp" not in canais:
            canais.append("wpp")
        for m in req.municipios:
            await monitoramentos_service.criar_busca(
                session,
                usuario_id,
                municipio_ibge=m.ibge,
                area=None,
                fonte=None,
                canais=canais,
            )

    return OnboardingResponse(municipios=len(req.municipios), sync_disparado=req.disparar_sync)
