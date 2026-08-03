"""Endpoints da agenda de contatos (RLS por usuario_id).

`DELETE` arquiva (tombstone) — a remoção definitiva acontece depois que o sync
propaga o delete para os provedores conectados.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.contato import (
    ContatoCreate,
    ContatoRead,
    ContatoUpdate,
    ImportacaoResultado,
    ImportacaoVcard,
)
from ...services import contatos as service
from ..deps import get_rls_db

router = APIRouter(tags=["contatos"])


async def _get_ou_404(session: AsyncSession, contato_id: uuid.UUID):
    contato = await service.obter(session, contato_id)
    if contato is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CONTATO_NAO_ENCONTRADO"
        )
    return contato


@router.get("/contatos", response_model=list[ContatoRead])
async def listar_contatos(
    busca: str | None = Query(default=None, description="nome, organização, cargo ou e-mail"),
    tag: str | None = Query(default=None),
    municipio: str | None = Query(default=None, description="código IBGE (7 dígitos)"),
    origem: str | None = Query(
        default=None, description="manual|google|microsoft|apple|carddav|vcard"
    ),
    arquivados: bool = Query(default=False),
    session: AsyncSession = Depends(get_rls_db),
) -> list[ContatoRead]:
    rows = await service.listar(
        session,
        busca=busca,
        tag=tag,
        municipio=municipio,
        origem=origem,
        incluir_arquivados=arquivados,
    )
    return [ContatoRead.model_validate(c) for c in rows]


@router.post("/contatos", response_model=ContatoRead, status_code=status.HTTP_201_CREATED)
async def criar_contato(
    body: ContatoCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> ContatoRead:
    contato = await service.criar(session, usuario_id=user.id, dados=body)
    return ContatoRead.model_validate(contato)


# Declarado ANTES de /contatos/{contato_id}: senão o path vira um uuid inválido.
@router.get("/contatos/exportar")
async def exportar_contatos(
    session: AsyncSession = Depends(get_rls_db),
) -> Response:
    """Exporta a agenda em .vcf — importável no Google/Apple/Outlook sem conectar conta."""
    contatos = await service.listar(session)
    return Response(
        content=service.exportar_vcf(contatos),
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contatos-hub-capture.vcf"'},
    )


@router.post("/contatos/importar", response_model=ImportacaoResultado)
async def importar_contatos(
    body: ImportacaoVcard,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_rls_db),
) -> ImportacaoResultado:
    return await service.importar_vcf(session, usuario_id=user.id, conteudo=body.conteudo)


@router.get("/contatos/{contato_id}", response_model=ContatoRead)
async def obter_contato(
    contato_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> ContatoRead:
    return ContatoRead.model_validate(await _get_ou_404(session, contato_id))


@router.patch("/contatos/{contato_id}", response_model=ContatoRead)
async def atualizar_contato(
    contato_id: uuid.UUID,
    body: ContatoUpdate,
    session: AsyncSession = Depends(get_rls_db),
) -> ContatoRead:
    contato = await _get_ou_404(session, contato_id)
    return ContatoRead.model_validate(await service.atualizar(session, contato, body))


@router.delete("/contatos/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_contato(
    contato_id: uuid.UUID,
    session: AsyncSession = Depends(get_rls_db),
) -> None:
    await service.arquivar(session, await _get_ou_404(session, contato_id))
