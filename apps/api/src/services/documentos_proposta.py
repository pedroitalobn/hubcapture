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

import asyncio
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

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


# ── A ponte do download ─────────────────────────────────────────────────────
#: extensão → content type, para quando a fonte não declara (o Struts costuma
#: mandar `application/octet-stream` em tudo). O nome do arquivo é o que o
#: gestor tem: se ele diz `.pdf`, o navegador dele deve abrir um PDF.
_TIPOS = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "csv": "text/csv",
    "zip": "application/zip",
    "rar": "application/vnd.rar",
    "7z": "application/x-7z-compressed",
    "p7s": "application/pkcs7-signature",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "rtf": "application/rtf",
}
_PADRAO = "application/octet-stream"


@dataclass(frozen=True)
class Referencia:
    """O que a ponte precisa para buscar UM arquivo — lido do cache, sob RLS."""

    id_proposta_fonte: str
    url: str
    nome: str


@dataclass(frozen=True)
class Arquivo:
    """Os bytes do documento, prontos para a resposta. Nada disso é gravado."""

    nome: str
    conteudo: bytes
    content_type: str


def _sanear(nome: str) -> str:
    """Nome de arquivo seguro para o `Content-Disposition`.

    O nome vem de HTML raspado: aspas e quebra de linha nele injetariam
    parâmetros no cabeçalho da resposta.
    """
    limpo = " ".join(str(nome or "").split()).replace('"', "").replace("\\", "_")
    limpo = limpo.replace("/", "_").strip(". ")
    return limpo[:180] or "documento"


def content_disposition(nome: str, *, inline: bool = False) -> str:
    """Cabeçalho de download com o nome ACENTUADO preservado.

    Duas formas no mesmo cabeçalho, como manda a RFC 6266: `filename` só-ASCII
    para o cliente antigo e `filename*` em UTF-8 para o resto. Sem o par, o
    "Ofício de Celebração.pdf" da fonte quebraria a resposta — cabeçalho HTTP
    é latin-1 — ou chegaria ao gestor com o nome mutilado.
    """
    seguro = _sanear(nome)
    ascii_ = unicodedata.normalize("NFKD", seguro).encode("ascii", "ignore").decode()
    ascii_ = "".join(c for c in ascii_ if c.isprintable()) or "documento"
    return (
        f'{"inline" if inline else "attachment"}; filename="{ascii_}"; '
        f"filename*=UTF-8''{quote(seguro)}"
    )


def content_type_de(nome: str, declarado: str | None) -> str:
    """O tipo do arquivo — a extensão do NOME vence o que o portal declarou.

    O Struts manda `application/octet-stream` até no PDF; com ele, o celular
    do gestor não abre o documento, só o guarda. `octet-stream` declarado com
    um nome `.pdf` é falta de informação da fonte, não informação.
    """
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    do_nome = _TIPOS.get(ext)
    if do_nome:
        return do_nome
    tipo = (declarado or "").split(";")[0].strip().lower()
    return tipo or _PADRAO


class SemArquivoNaFonte(LookupError):
    """A fonte lista o documento mas não publica endereço para baixá-lo.

    É diferente de "a fonte caiu" (`DocumentoIndisponivel`, 502): aqui não há o
    que buscar, e o gestor pede o arquivo ao órgão pelo nome exato.
    """


#: Cada download levanta um Chromium (o rito do acesso livre depende de JS).
#: Sem teto, três cliques simultâneos disputariam a CPU do container com a
#: coleta e derrubariam o painel inteiro — a lição da §38, aplicada aqui.
_PONTES = asyncio.Semaphore(2)


async def referencia(
    session: AsyncSession, proposta: Proposta, documento_id: uuid.UUID
) -> Referencia | None:
    """O que a ponte precisa saber, lido sob a sessão RLS. `None` = o documento
    não é desta proposta (ou não está no cache do território).

    A URL NUNCA vem do cliente: sai do documento já cacheado para esta
    proposta, senão o endpoint viraria um proxy aberto.
    """
    documento = next(
        (d for d in await listar(session, proposta) if d.id == documento_id), None
    )
    if documento is None:
        return None
    if not documento.url:
        raise SemArquivoNaFonte(
            "a fonte não publicou endereço de download para este documento"
        )
    id_siconv = documento.id_proposta_fonte or id_siconv_de(proposta)
    if not id_siconv:
        raise SemArquivoNaFonte(
            "esta proposta não expõe o identificador que o portal exige"
        )
    return Referencia(id_proposta_fonte=id_siconv, url=documento.url, nome=documento.nome)


async def buscar(ref: Referencia) -> Arquivo:
    """Os bytes, pela sessão de acesso livre da fonte. NÃO toca o banco.

    Separado de `referencia` de propósito (§38): o browser leva segundos, e
    segurar a conexão RLS do request durante a coleta é o que esgota o pool e
    faz o painel inteiro esperar. Falha da FONTE sobe como
    `DocumentoIndisponivel` — quem falhou foi ela.
    """
    async with _PONTES:
        conteudo, tipo, nome_fonte = await pareceres_siconv.get_connector().baixar_documento(
            ref.id_proposta_fonte, ref.url
        )
    nome = _sanear(nome_fonte or ref.nome)
    return Arquivo(nome=nome, conteudo=conteudo, content_type=content_type_de(nome, tipo))
