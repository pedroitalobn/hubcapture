"""Documentos digitalizados da proposta — cache-first, com o arquivo da fonte.

"Quando o status da publicação for publicado, disponibilizar o arquivo"
(ponto 10 do feedback de 28/08). O documento é o que o gestor anexa ao
processo e leva para a reunião; a tela dizia "Publicado" e parava ali, com o
PDF a três cliques dentro do portal.

Guardamos a REFERÊNCIA (nome, data, URL na fonte) e não os bytes: o arquivo é
público na origem, e cachear binário de terceiro cria acervo que ninguém pediu
para manter — além de envelhecer sem aviso quando a fonte republica.

Só o universo SIconv (discricionárias/legais) tem esta lista hoje. Para as
demais fontes a resposta é `fonte_nao_suportada` — que é diferente de "esta
proposta não tem documento", e a tela precisa dessa diferença.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors import pareceres_siconv
from ..ingestion.normalizer_documento import normalize_documento
from ..models.proposta import Proposta
from ..models.proposta_documento import PropostaDocumento
from ..schemas.documento import DocumentoColeta, DocumentoRead
from . import municipios as municipios_service
from ._sync import registrar_sync

#: TTL do cache-first. Documento digitalizado entra em dias, não em minutos.
TTL_HORAS = 12

SOURCE_ID = pareceres_siconv.SOURCE_ID_DOCUMENTO

_UPSERT_FIELDS = (
    "numero_proposta",
    "id_proposta_fonte",
    "municipio_ibge",
    "nome",
    "tipo",
    "data_upload",
    "url",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)

#: ordem de exibição: a publicação primeiro — é o documento que o gestor
#: procura quando a proposta acaba de sair no diário oficial.
_PESO_TIPO = {"publicacao": 0, "contrato": 1, "termo": 2, "oficio": 3}


def id_siconv_de(proposta: Proposta) -> str | None:
    """O idProposta INTERNO do SIconv — a chave que o webapp exige.

    Nas cargas do pacote diário ele é o próprio `id_externo`. Número de
    protocolo ("028666/2026") não serve: o webapp só aceita o id numérico.
    """
    externo = str(proposta.id_externo or "").strip()
    return externo if externo.isdigit() else None


def _e_siconv(proposta: Proposta) -> bool:
    if proposta.fonte in ("transferegov_disc", "transferegov_voluntarias"):
        return True
    dados = proposta.dados_fonte if isinstance(proposta.dados_fonte, dict) else {}
    return str(dados.get("_carga") or "").startswith("siconv")


async def listar(session: AsyncSession, proposta: Proposta) -> list[PropostaDocumento]:
    """Documentos já cacheados da proposta (publicação primeiro, mais recentes
    antes)."""
    condicoes = []
    id_siconv = id_siconv_de(proposta)
    if id_siconv:
        condicoes.append(PropostaDocumento.id_proposta_fonte == id_siconv)
    if proposta.numero_proposta:
        condicoes.append(PropostaDocumento.numero_proposta == proposta.numero_proposta)
    if not condicoes:
        return []
    rows = (
        (await session.execute(select(PropostaDocumento).where(or_(*condicoes))))
        .scalars()
        .all()
    )
    return sorted(
        rows,
        key=lambda d: (
            _PESO_TIPO.get(d.tipo or "", 9),
            -(d.data_upload.toordinal() if d.data_upload else 0),
            d.nome,
        ),
    )


def _esta_fresco(itens: list[PropostaDocumento]) -> bool:
    if not itens:
        return False
    limite = datetime.now(UTC) - timedelta(hours=TTL_HORAS)
    return all(x.cache_atualizado_em and x.cache_atualizado_em >= limite for x in itens)


async def _upsert(session: AsyncSession, canonicos: list) -> None:
    now = datetime.now(UTC)
    for c in canonicos:
        values = c.model_dump()
        values["cache_atualizado_em"] = now
        stmt = pg_insert(PropostaDocumento).values(**values)
        update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
        update_set["cache_atualizado_em"] = now
        update_set["updated_at"] = now
        stmt = stmt.on_conflict_do_update(
            constraint="uq_proposta_documentos_fonte_id_externo", set_=update_set
        )
        await session.execute(stmt)


async def sync_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    usuario_id: uuid.UUID | None = None,
) -> DocumentoColeta:
    """Coleta na fonte e grava. Falha vira status + `sync_runs`, nunca 500."""
    if not _e_siconv(proposta):
        return DocumentoColeta(status="fonte_nao_suportada", total=0)
    id_siconv = id_siconv_de(proposta)
    if not id_siconv:
        return DocumentoColeta(status="sem_chave", total=0)

    iniciado = datetime.now(UTC)
    try:
        brutos = await pareceres_siconv.get_connector().documentos_por_id_proposta(id_siconv)
    except Exception as exc:  # noqa: BLE001 — fonte de governo cai; o painel não
        erro = f"{type(exc).__name__}: {exc}"
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=SOURCE_ID,
            tipo="avulso",
            status="erro",
            registros=0,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=erro[:1000],
        )
        return DocumentoColeta(status="erro", total=0, erro=erro[:500])

    canonicos = [
        c
        for c in (
            normalize_documento(
                b,
                fonte=SOURCE_ID,
                id_proposta_fonte=id_siconv,
                numero_proposta=proposta.numero_proposta,
                municipio_ibge=proposta.municipio_ibge,
            )
            for b in brutos
        )
        if c is not None
    ]
    if canonicos:
        await _upsert(session, canonicos)
    await registrar_sync(
        usuario_id=usuario_id,
        fonte=SOURCE_ID,
        tipo="avulso",
        status="ok",
        registros=len(canonicos),
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
        erro=None,
    )
    return DocumentoColeta(status="ok", total=len(canonicos))


async def por_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
) -> tuple[list[DocumentoRead], DocumentoColeta]:
    """Cache-first: responde do cache e só vai à fonte quando ele venceu.

    Incidente de coleta NÃO apaga o que já está em cache — a tela continua
    mostrando o documento de ontem com o aviso de que a fonte não respondeu
    hoje, que é o oposto de dizer que a proposta não tem documento.
    """
    itens = await listar(session, proposta)
    coleta = DocumentoColeta(status="ok", total=len(itens))
    if atualizar or not _esta_fresco(itens):
        coleta = await sync_proposta(session, proposta, usuario_id=usuario_id)
        if coleta.status in ("ok", "erro"):
            itens = await listar(session, proposta)
        coleta.total = len(itens)
    lidos = [DocumentoRead.model_validate(d) for d in itens]
    return await municipios_service.enriquecer(session, lidos), coleta
