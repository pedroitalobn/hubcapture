"""Andamento da proposta — linha do tempo e emenda/parlamentar autor.

Rotas em inglês (§25): andamento → timeline, emendas → amendments.

Gate por ENDPOINT, não por router (§40): ler o andamento do cache é Meu painel
— o detalhe da proposta não pode esvaziar porque a captação está desligada. O
que pertence ao módulo é a EXPLORAÇÃO ativa: com `captacao` desligado o
`atualizar=true` é ignorado e a resposta vem do cache, dizendo que veio.
"""

from __future__ import annotations

import logging
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

log = logging.getLogger(__name__)

router = APIRouter(tags=["andamento"])

_NAO_ENCONTRADA = "Proposta não encontrada no seu território."
_NAO_ENCONTRADO = "Documento não encontrado nesta proposta."


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


@router.get("/proposals/{proposta_id}/documents/{documento_id}/file")
async def arquivo_do_documento(
    proposta_id: uuid.UUID,
    documento_id: uuid.UUID,
    inline: bool = Query(default=False, description="abrir no visualizador em vez de baixar"),
    session: AsyncSession = Depends(get_rls_db),
    usuario: Usuario = Depends(current_active_user),
) -> Response:
    """O ARQUIVO do documento digitalizado, servido pela ponte do Hub.

    O endereço que a fonte publica na lista não é um link público: é uma ação
    do webapp do Transferegov, válida só dentro da sessão. Aberto no navegador
    do gestor ele cai no SSO (`idp.transferegov.sistema.gov.br/idp/`) e a
    resposta ao "Baixar" vira uma tela de login. Aqui o Hub refaz o rito do
    acesso livre, baixa pela mesma sessão e devolve os bytes.

    Ponte, não acervo (§56): nada é persistido. A URL nunca vem do cliente —
    sai do documento que já está no cache DESTA proposta, sob RLS.

    Leitura de cache, logo panel-core (§40): não depende do módulo captação.
    """
    from ...connectors import pareceres_siconv
    from ...services import documentos_proposta as documentos_service

    try:
        ref = await service.referencia_do_documento(session, proposta_id, documento_id)
    except documentos_service.SemArquivoNaFonte as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"DOCUMENTO_SEM_ARQUIVO: {exc}"
        ) from exc
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADO)

    # a coleta é I/O externo de segundos: a conexão RLS volta ao pool ANTES
    # dela, senão um download segura o painel inteiro (§38)
    await session.close()
    try:
        arquivo = await documentos_service.buscar(ref)
    except pareceres_siconv.DocumentoIndisponivel as exc:
        # 502: a falha é da FONTE. O front diz isso ao gestor em vez de
        # sugerir que o documento não existe.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — browser/SSO caem; 500 não explica
        log.warning("documento %s: ponte de download falhou", documento_id, exc_info=True)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="não foi possível baixar o arquivo no portal do Transferegov agora",
        ) from exc
    return Response(
        content=arquivo.conteudo,
        media_type=arquivo.content_type,
        headers={
            "Content-Disposition": documentos_service.content_disposition(
                arquivo.nome, inline=inline
            ),
            # o arquivo é da FONTE e pode ser republicado sem aviso
            "Cache-Control": "no-store",
        },
    )


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
