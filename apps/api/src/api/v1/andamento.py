"""Andamento da proposta — linha do tempo e emenda/parlamentar autor.

Rotas em inglês (§25): andamento → timeline, emendas → amendments.

Gate por ENDPOINT, não por router (§40): ler o andamento do cache é Meu painel
— o detalhe da proposta não pode esvaziar porque a captação está desligada. O
que pertence ao módulo é a EXPLORAÇÃO ativa: com `captacao` desligado o
`atualizar=true` é ignorado e a resposta vem do cache, dizendo que veio.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...schemas.andamento import AndamentoPagina
from ...schemas.documento import DocumentoPagina
from ...schemas.emenda import EmendaPagina
from ...schemas.empenho import EmpenhoPagina
from ...schemas.publicacao import PublicacaoPagina
from ...services import andamento as service
from ...services import modulos as modulos_service
from ..deps import get_rls_db

router = APIRouter(tags=["andamento"])

_NAO_ENCONTRADA = "Proposta não encontrada no seu território."


def _iso(valor: str | None) -> date | None:
    """Data ISO do carimbo → `date` (só para nomear o arquivo baixado)."""
    try:
        return date.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


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


@router.get("/proposals/{proposta_id}/publication", response_model=PublicacaoPagina)
async def publicacao_da_proposta(
    proposta_id: uuid.UUID,
    conferir: bool = Query(
        default=False, description="conferir a publicação no DOU Seção 3 agora"
    ),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> PublicacaoPagina:
    """"Saiu ou não saiu?" — a leitura e as PROVAS que a sustentam (§56c).

    Reúne o campo da ficha, o PDF da publicação anexado e o extrato no DOU, e
    mostra todos, inclusive quando discordam. `conferir=true` é consulta ATIVA
    (vai ao DOU agora) e por isso obedece ao gate do módulo captação; sem ele a
    resposta sai do cache — ler o estado da publicação é Meu painel (§40).
    """
    pagina = await service.publicacao(
        session, proposta_id, conferir=await _pode_consultar_fonte(conferir)
    )
    if pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    return pagina


@router.get("/proposals/{proposta_id}/publication/pdf")
async def pdf_da_publicacao(
    proposta_id: uuid.UUID,
    inline: bool = Query(default=False, description="abrir no visualizador em vez de baixar"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> Response:
    """O PDF CERTIFICADO da página do DOU onde o extrato saiu (§56c).

    É o comprovante da publicação — o que o gestor anexa ao processo e manda
    para o jurídico; a página web do in.gov.br não é documento assinado. O Hub
    só faz a PONTE (nada é persistido, §56): a referência é a URL da fonte e os
    bytes vêm dela na hora, para o gestor não precisar atravessar o
    visualizador. Se a fonte não entregar, a tela cai para o link direto.

    Leitura de cache, logo panel-core (§40): não depende do módulo captação —
    quem conferiu no DOU foi o `?conferir=true` do endpoint irmão.
    """
    from ...connectors import dou as dou_connector

    pagina = await service.publicacao(session, proposta_id)
    if pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADA)
    prova = pagina.publicacao.prova
    if prova is None or not prova.pdf_url:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                "PUBLICACAO_SEM_PDF: esta proposta ainda não tem extrato do DOU "
                "conferido — use a conferência no Diário Oficial primeiro"
            ),
        )
    try:
        conteudo = await dou_connector.baixar_pdf(prova.pdf_url)
    except dou_connector.DouIndisponivel as exc:
        # 502: quem falhou foi a FONTE, não o pedido. O front distingue e
        # oferece o link direto em vez de dizer que a publicação não existe.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    nome = dou_connector.nome_arquivo_pdf(
        prova.secao, _iso(prova.data), prova.pagina
    )
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{nome}"',
        },
    )


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
