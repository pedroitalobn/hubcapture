"""API de integração (§67): chaves de API, "quem sou eu" e reset do sandbox.

Três públicos:
- **a conta** (`/account/api-keys`): o próprio cliente emite e revoga as
  chaves dele, se o PLANO incluir a feature `api` (no sandbox, sempre);
- **a administração** (`/admin/api-keys`): emite chave para qualquer conta,
  com limites próprios, e revoga;
- **o sistema parceiro** (`/developer/me`, `/developer/sandbox/reset`): confere
  com qual conta/chave está falando e, no sandbox, recria os dados de teste.

A gestão de chaves exige login do painel (JWT): o middleware de limite
(`core/limite_api.py`) recusa `/account` e `/admin` para quem chega por chave —
chave não emite chave.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import limite_api
from ...core.config import settings
from ...core.users import current_active_user, current_superuser
from ...models.api_chave import ApiChave
from ...models.municipio_interesse import MunicipioInteresse
from ...models.usuario import Usuario
from ...schemas.api_chaves import (
    AdminApiChaveCreate,
    ApiChaveCreate,
    ApiChaveCriada,
    ApiChaveRead,
    ChaveAtual,
    ChavesDaConta,
    DeveloperMe,
    SandboxReset,
)
from ...services import api_chaves as service
from ...services import plano_gates
from ...services.demo import bloquear_escrita
from ..deps import get_platform_db, get_rls_db

router = APIRouter(tags=["integracao"])
log = logging.getLogger("hubcapture.api_parceiros")


async def _ler(
    session: AsyncSession, pares: list[tuple[ApiChave, Usuario]], *, com_dono: bool
) -> list[ApiChaveRead]:
    """Registros → leitura, com limites EFETIVOS e o consumo (inclusive o que
    ainda está em memória, esperando a próxima gravação em lote)."""
    hoje = datetime.now(UTC).date()
    uso = await service.uso_por_chave(session, [c.id for c, _ in pares], hoje - timedelta(days=29))
    pendente = limite_api.consumo.contagens
    agora = datetime.now(UTC)
    saida: list[ApiChaveRead] = []
    for chave, dono in pares:
        cfg = await plano_gates.config_por_plano_id(dono.plano_id)
        linhas = uso.get(chave.id, [])
        ok_hoje, bloq_hoje = pendente.get((chave.id, hoje), [0, 0])
        for linha in linhas:
            if linha.dia == hoje:
                ok_hoje += linha.requisicoes
                bloq_hoje += linha.bloqueadas
        total_30 = (
            sum(linha.requisicoes for linha in linhas) + pendente.get((chave.id, hoje), [0, 0])[0]
        )
        saida.append(
            ApiChaveRead(
                id=chave.id,
                nome=chave.nome,
                prefixo=chave.prefixo,
                ambiente=chave.ambiente,
                escopo=chave.escopo,
                ativa=chave.revogada_em is None
                and (chave.expira_em is None or chave.expira_em > agora),
                limite_por_minuto=chave.limite_por_minuto
                or cfg.api_req_min
                or settings.api_limite_por_minuto,
                limite_por_dia=chave.limite_por_dia
                or cfg.api_req_dia
                or settings.api_limite_por_dia,
                uso_hoje=ok_hoje,
                bloqueadas_hoje=bloq_hoje,
                uso_30_dias=total_30,
                ultimo_uso_em=chave.ultimo_uso_em,
                expira_em=chave.expira_em,
                revogada_em=chave.revogada_em,
                created_at=chave.created_at,
                usuario_id=dono.id if com_dono else None,
                usuario_email=dono.email if com_dono else None,
            )
        )
    return saida


async def _preparar_sandbox(usuario_id: uuid.UUID) -> None:
    """No sandbox, a conta que ganha chave ganha também dados de teste."""
    if not settings.sandbox:
        return
    from ...services import sandbox as sandbox_service

    try:
        await sandbox_service.preparar_conta(usuario_id)
    except Exception:  # noqa: BLE001 — a chave vale mesmo sem os dados de exemplo
        log.warning("sandbox: falha ao semear a conta %s", usuario_id, exc_info=True)


async def _disponibilidade(session: AsyncSession, user: Usuario) -> tuple[bool, str | None, int]:
    cfg = await plano_gates.config_do_usuario(session, user.id)
    maximo = (
        cfg.api_chaves_max if cfg.api_chaves_max is not None else settings.api_chaves_max_por_conta
    )
    if user.is_superuser:
        return False, "Contas de administração não recebem chave de API.", maximo
    if getattr(user, "is_demo", False):
        return False, "A conta de demonstração não emite chaves de API.", maximo
    if settings.sandbox or plano_gates.feature_liberada(cfg, "api"):
        return True, None, maximo
    return False, "O seu plano não inclui a API de integração.", maximo


# ── Conta (self-service) ────────────────────────────────────────────────────
@router.get("/account/api-keys", response_model=ChavesDaConta)
async def minhas_chaves(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> ChavesDaConta:
    disponivel, motivo, maximo = await _disponibilidade(session, user)
    pares = await service.listar(session, user.id)
    return ChavesDaConta(
        disponivel=disponivel,
        motivo=motivo,
        ambiente=service.ambiente_atual(),
        sandbox=settings.sandbox,
        maximo=maximo,
        chaves=await _ler(session, pares, com_dono=False),
    )


@router.post(
    "/account/api-keys", response_model=ApiChaveCriada, status_code=status.HTTP_201_CREATED
)
async def criar_minha_chave(
    body: ApiChaveCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> ApiChaveCriada:
    bloquear_escrita(user)
    disponivel, motivo, _ = await _disponibilidade(session, user)
    if not disponivel:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"FEATURE_NAO_INCLUIDA_PLANO: api — {motivo}"
        )
    try:
        registro, texto = await service.criar(
            session,
            user,
            nome=body.nome,
            escopo=body.escopo,
            criada_por=user.id,
            expira_em=body.expira_em,
        )
    except service.LimiteChavesExcedido as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"LIMITE_PLANO_API_CHAVES: máximo de {exc.maximo} chave(s) ativa(s)",
        ) from exc
    except service.ChaveInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _preparar_sandbox(user.id)
    lida = (await _ler(session, [(registro, user)], com_dono=False))[0]
    return ApiChaveCriada(**lida.model_dump(), chave=texto)


@router.delete("/account/api-keys/{chave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revogar_minha_chave(
    chave_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    if not await service.revogar(session, chave_id, usuario_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chave não encontrada ou já revogada")


# ── Administração ───────────────────────────────────────────────────────────
@router.get("/admin/api-keys", response_model=list[ApiChaveRead])
async def admin_listar_chaves(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ApiChaveRead]:
    return await _ler(session, await service.listar(session), com_dono=True)


@router.post("/admin/api-keys", response_model=ApiChaveCriada, status_code=status.HTTP_201_CREATED)
async def admin_criar_chave(
    body: AdminApiChaveCreate,
    admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> ApiChaveCriada:
    dono = await session.get(Usuario, body.usuario_id)
    if dono is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="usuário não encontrado")
    try:
        registro, texto = await service.criar(
            session,
            dono,
            nome=body.nome,
            escopo=body.escopo,
            criada_por=admin.id,
            limite_por_minuto=body.limite_por_minuto,
            limite_por_dia=body.limite_por_dia,
            expira_em=body.expira_em,
            respeitar_limite_plano=False,  # a administração decide caso a caso
        )
    except service.ChaveInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _preparar_sandbox(dono.id)
    lida = (await _ler(session, [(registro, dono)], com_dono=True))[0]
    return ApiChaveCriada(**lida.model_dump(), chave=texto)


@router.delete("/admin/api-keys/{chave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_revogar_chave(
    chave_id: uuid.UUID,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    if not await service.revogar(session, chave_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chave não encontrada ou já revogada")


# ── Sistema parceiro ────────────────────────────────────────────────────────
@router.get("/developer/me", response_model=DeveloperMe)
async def quem_sou_eu(
    request: Request,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> DeveloperMe:
    """Com qual conta (e chave) esta integração está falando — o 1º teste."""
    municipios = (
        (
            await session.execute(
                select(MunicipioInteresse.ibge)
                .where(MunicipioInteresse.usuario_id == user.id)
                .order_by(MunicipioInteresse.ibge)
            )
        )
        .scalars()
        .all()
    )
    chave = getattr(request.state, "api_chave", None)
    return DeveloperMe(
        ambiente=service.ambiente_atual(),
        sandbox=settings.sandbox,
        autenticacao="api_key" if chave else "jwt",
        usuario_id=user.id,
        email=user.email,
        nome=user.nome,
        municipios=list(municipios),
        chave=ChaveAtual(
            prefixo=chave.prefixo,
            nome=chave.nome,
            escopo=chave.escopo,
            limite_por_minuto=chave.limite_por_minuto,
            limite_por_dia=chave.limite_por_dia,
        )
        if chave
        else None,
    )


@router.post("/developer/sandbox/reset", response_model=SandboxReset)
async def resetar_sandbox(user: Usuario = Depends(current_active_user)) -> SandboxReset:
    """Só no sandbox: apaga a curadoria da conta e recria os dados de teste."""
    if not settings.sandbox:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="SANDBOX_DESATIVADO")
    from ...services import sandbox as sandbox_service

    n = await sandbox_service.resetar_conta(user.id)
    return SandboxReset(
        municipios=n,
        mensagem="Dados de teste recriados: favoritos, pastas, monitoramentos e alertas zerados.",
    )
