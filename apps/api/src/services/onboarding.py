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
from ..models.preferencias import PreferenciasUsuario
from ..models.usuario import Usuario
from ..schemas.curadoria import OnboardingRequest, OnboardingResponse
from . import fontes as fontes_service
from . import monitoramentos as monitoramentos_service
from . import plano_gates


class LimitePlanoExcedido(Exception):
    """Municípios além do limite do plano (config `municipios_max`)."""

    def __init__(self, maximo: int) -> None:
        self.maximo = maximo
        super().__init__(f"limite de {maximo} município(s) do plano excedido")


def excede_limite(cfg: plano_gates.PlanoConfig, existentes: set[str], novos: set[str]) -> bool:
    """O território resultante passa do `municipios_max` do plano? Sem limite → nunca.

    Regra ÚNICA do limite de municípios: vale para o onboarding e para o
    "adicionar município" de Minha conta — os dois caminhos não podem divergir.
    Município que já está no território não conta duas vezes.
    """
    maximo = cfg.municipios_max
    if not maximo:  # None/0 = ilimitado (mesma leitura de sempre do onboarding)
        return False
    return len(existentes | novos) > int(maximo)


async def ibges_do_territorio(session: AsyncSession, usuario_id: uuid.UUID) -> set[str]:
    return set(
        (
            await session.execute(
                select(MunicipioInteresse.ibge).where(MunicipioInteresse.usuario_id == usuario_id)
            )
        )
        .scalars()
        .all()
    )


async def _validar_limite_municipios(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    req: OnboardingRequest,
    cfg: plano_gates.PlanoConfig,
) -> None:
    """3 tiers × quantidade de municípios (fluxograma): o plano limita quantos
    municípios o usuário monitora. Sem plano/limite → ilimitado."""
    if not cfg.municipios_max:
        return
    existentes = await ibges_do_territorio(session, usuario_id)
    if excede_limite(cfg, existentes, {m.ibge for m in req.municipios}):
        raise LimitePlanoExcedido(int(cfg.municipios_max))


async def onboarding(
    session: AsyncSession, *, usuario_id: uuid.UUID, req: OnboardingRequest
) -> OnboardingResponse:
    # config do plano do usuário (§39): limita municípios e recorta fontes
    cfg = await plano_gates.config_do_usuario(session, usuario_id)
    await _validar_limite_municipios(session, usuario_id, req, cfg)

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
    # descarta fonte fora do recorte da v1 (`services/fontes.py`) e fora do
    # PLANO do usuário (§39). O fallback "todas" também respeita o plano.
    fontes_escolhidas = plano_gates.filtrar_fontes(
        cfg, fontes_service.expandir(req.fontes) or list(fontes_service.HABILITADAS)
    )

    prefs = pg_insert(PreferenciasUsuario).values(
        usuario_id=usuario_id,
        fontes=fontes_escolhidas,
        areas=req.areas,
        monitorar_ativo=req.monitorar_ativo,
        # o e-mail escolhido no onboarding vale para a CONTA (§63), não só
        # para as buscas: sem isto, o alerta de uma proposta favoritada
        # depois nunca ia por e-mail
        canais_alerta=["email"] if "email" in (req.canais_alerta or []) else [],
    )
    prefs = prefs.on_conflict_do_update(
        index_elements=["usuario_id"],
        set_={
            "fontes": prefs.excluded.fontes,
            "areas": prefs.excluded.areas,
            "monitorar_ativo": prefs.excluded.monitorar_ativo,
            "canais_alerta": prefs.excluded.canais_alerta,
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
