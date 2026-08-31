"""Andamento da proposta — linha do tempo e emenda/parlamentar autor.

Rotas em inglês (§25): andamento → timeline, emendas → amendments.

Gate por ENDPOINT, não por router (§40): ler o andamento do cache é Meu painel
— o detalhe da proposta não pode esvaziar porque a captação está desligada. O
que pertence ao módulo é a EXPLORAÇÃO ativa: com `captacao` desligado o
`atualizar=true` é ignorado e a resposta vem do cache, dizendo que veio.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.andamento import AndamentoPagina
from ...schemas.documento import DocumentoPagina
from ...schemas.emenda import EmendaPagina
from ...schemas.empenho import EmpenhoPagina
from ...services import andamento as service
from ...services import modulos as modulos_service
from ..deps import get_rls_db

router = APIRouter(tags=["andamento"])

_NAO_ENCONTRADA = "Proposta não encontrada no seu território."


async def _pode_consultar_fonte(atualizar: bool) -> bool:
    """Consulta ao vivo é exploração — só com o módulo captação ligado."""
    return bool(atualizar) and await modulos_service.esta_ativo("captacao")


@router.get("/proposals/{proposta_id}/timeline", response_model=AndamentoPagina)
async def timeline_da_proposta(
    proposta_id: uuid.UUID,
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> AndamentoPagina:
    """Tramitação em ordem cronológica: pareceres, vigência, prazos e pendências."""
    pagina = await service.linha_do_tempo(
        session,
        proposta_id,
        atualizar=await _pode_consultar_fonte(atualizar),
        usuario_id=usuario.id,
    )
    if pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    return pagina


@router.get("/proposals/{proposta_id}/commitments", response_model=EmpenhoPagina)
async def empenhos_da_proposta(
    proposta_id: uuid.UUID,
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> EmpenhoPagina:
    """Empenhos da proposta e os totais — o recurso saiu do papel ou não."""
    resultado = await service.empenhos(
        session,
        proposta_id,
        atualizar=await _pode_consultar_fonte(atualizar),
        usuario_id=usuario.id,
    )
    if resultado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    itens, resumo, coleta = resultado
    return EmpenhoPagina(itens=itens, resumo=resumo, coleta=coleta)


@router.get("/proposals/{proposta_id}/documents", response_model=DocumentoPagina)
async def documentos_da_proposta(
    proposta_id: uuid.UUID,
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> DocumentoPagina:
    """Documentos digitalizados: a publicação, o contrato assinado, os ofícios.

    É o arquivo que comprova o ato — quando a proposta sai publicada, é isso
    que o gestor precisa em mãos (ponto 10 do feedback).
    """
    resultado = await service.documentos(
        session,
        proposta_id,
        atualizar=await _pode_consultar_fonte(atualizar),
        usuario_id=usuario.id,
    )
    if resultado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    itens, coleta = resultado
    return DocumentoPagina(itens=itens, coleta=coleta)


@router.get("/proposals/{proposta_id}/amendments", response_model=EmendaPagina)
async def emendas_da_proposta(
    proposta_id: uuid.UUID,
    atualizar: bool = Query(default=False, description="forçar coleta na fonte"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> EmendaPagina:
    """Qual emenda banca esta proposta e quem é o parlamentar autor."""
    resultado = await service.emendas(
        session,
        proposta_id,
        atualizar=await _pode_consultar_fonte(atualizar),
        usuario_id=usuario.id,
    )
    if resultado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    itens, coleta = resultado
    return EmendaPagina(itens=itens, coleta=coleta)
