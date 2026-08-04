"""Conexão e sincronização das agendas externas (Google/Microsoft/Apple/CardDAV).

Nenhum endpoint devolve credencial: a resposta é sempre status + placar do sync.
Falha de provedor vira `SyncResultado.status='erro'` (200), não 500 — o painel
mostra o motivo e o resto da agenda segue funcionando.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.contato import (
    AutorizacaoOAuth,
    CallbackOAuth,
    ConectarSenhaApp,
    IntegracaoRead,
    IntegracaoUpdate,
    ProvedorInfo,
    SyncResultado,
)
from ...services import contatos_sync as sync_service
from ...services import integracoes_contatos as service
from ...services.modulos import require_modulo
from ..deps import get_rls_db

# Mesmo módulo da agenda: desligou contatos, some também a conexão de agendas.
router = APIRouter(
    tags=["integracoes"],
    prefix="/integrations/contacts",
    dependencies=[Depends(require_modulo("contatos"))],
)


async def _get_ou_404(session: AsyncSession, integracao_id: uuid.UUID):
    integracao = await service.obter(session, integracao_id)
    if integracao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="INTEGRACAO_NAO_ENCONTRADA"
        )
    return integracao


def _erro(exc: service.IntegracaoErro) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/providers", response_model=list[ProvedorInfo])
async def listar_provedores(
    _: Usuario = Depends(current_active_user),
) -> list[ProvedorInfo]:
    """Catálogo de agendas suportadas + se a credencial de aplicação está posta."""
    return await service.catalogo()


@router.get("", response_model=list[IntegracaoRead])
async def listar_integracoes(
    session: AsyncSession = Depends(get_rls_db),
) -> list[IntegracaoRead]:
    return [IntegracaoRead.model_validate(i) for i in await service.listar(session)]


@router.post("/callback", response_model=IntegracaoRead)
async def concluir_oauth(
    body: CallbackOAuth,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> IntegracaoRead:
    """Troca o `code` do provedor por tokens e grava a conta conectada."""
    try:
        integracao = await service.finalizar_oauth(session, usuario_id=user.id, callback=body)
    except service.IntegracaoErro as exc:
        raise _erro(exc) from exc
    return IntegracaoRead.model_validate(integracao)


@router.post("/sync", response_model=list[SyncResultado])
async def sincronizar_todas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> list[SyncResultado]:
    return await sync_service.sincronizar_todas(session, usuario_id=user.id)


@router.post("/{provedor}/authorize", response_model=AutorizacaoOAuth)
async def autorizar(
    provedor: str,
    redirect_uri: str | None = None,
    user: Usuario = Depends(current_active_user),
) -> AutorizacaoOAuth:
    """URL de consentimento do provedor (o web redireciona o usuário para ela)."""
    try:
        return await service.iniciar_oauth(
            provedor=provedor, usuario_id=user.id, redirect_uri=redirect_uri
        )
    except service.IntegracaoErro as exc:
        raise _erro(exc) from exc


@router.post("/{provedor}/app-password", response_model=IntegracaoRead)
async def conectar_senha_app(
    provedor: str,
    body: ConectarSenhaApp,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> IntegracaoRead:
    """Apple/iCloud e CardDAV genérico: conta + senha de app (validadas na hora)."""
    try:
        integracao = await service.conectar_senha_app(
            session, usuario_id=user.id, provedor=provedor, dados=body
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="PROVEDOR_DESCONHECIDO"
        ) from exc
    except service.IntegracaoErro as exc:
        raise _erro(exc) from exc
    return IntegracaoRead.model_validate(integracao)


@router.patch("/{integracao_id}", response_model=IntegracaoRead)
async def atualizar_integracao(
    integracao_id: uuid.UUID,
    body: IntegracaoUpdate,
    session: AsyncSession = Depends(get_rls_db),
) -> IntegracaoRead:
    integracao = await _get_ou_404(session, integracao_id)
    return IntegracaoRead.model_validate(await service.atualizar(session, integracao, body))


@router.delete("/{integracao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desconectar(
    integracao_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    """Desconecta a conta. Os contatos já sincronizados ficam na agenda do Hub."""
    await service.desconectar(session, await _get_ou_404(session, integracao_id))


@router.post("/{integracao_id}/sync", response_model=SyncResultado)
async def sincronizar(
    integracao_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> SyncResultado:
    integracao = await _get_ou_404(session, integracao_id)
    return await sync_service.sincronizar(
        session, usuario_id=user.id, integracao=integracao
    )
