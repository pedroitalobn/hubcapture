"""Agenda de contatos — CRUD, busca, dedup e import/export vCard.

Dado por-tenant: toda query roda na sessão com RLS (`get_rls_db`), então o
filtro por usuário é do banco, não do Python. `usuario_id` só é passado no
INSERT (a policy exige `WITH CHECK`).

Remoção é ARQUIVAMENTO: o contato vira tombstone para o sync conseguir propagar
o delete aos provedores conectados antes de sumir de vez.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ingestion.normalizer_contato import (
    aplicar_no_modelo,
    calcular_chave_dedup,
    canonizar,
    do_modelo,
    mesclar,
)
from ..integrations.contatos import vcard
from ..models.contato import Contato
from ..schemas.contato import (
    ContatoCanonico,
    ContatoCreate,
    ContatoUpdate,
    ImportacaoResultado,
)


async def listar(
    session: AsyncSession,
    *,
    busca: str | None = None,
    tag: str | None = None,
    municipio: str | None = None,
    origem: str | None = None,
    incluir_arquivados: bool = False,
) -> list[Contato]:
    stmt = select(Contato)
    if not incluir_arquivados:
        stmt = stmt.where(Contato.arquivado.is_(False))
    if municipio:
        stmt = stmt.where(Contato.municipio_ibge == municipio)
    if origem:
        stmt = stmt.where(Contato.origem == origem)
    if tag:
        stmt = stmt.where(Contato.tags.any(tag))
    if busca:
        alvo = f"%{busca.strip()}%"
        stmt = stmt.where(
            or_(
                Contato.nome.ilike(alvo),
                Contato.sobrenome.ilike(alvo),
                Contato.organizacao.ilike(alvo),
                Contato.cargo.ilike(alvo),
                Contato.chave_dedup.ilike(alvo),
            )
        )
    stmt = stmt.order_by(Contato.nome, Contato.sobrenome.nullslast())
    return list((await session.execute(stmt)).scalars().all())


async def obter(session: AsyncSession, contato_id: uuid.UUID) -> Contato | None:
    return (
        await session.execute(select(Contato).where(Contato.id == contato_id))
    ).scalar_one_or_none()


async def criar(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    dados: ContatoCreate,
    origem: str = "manual",
) -> Contato:
    contato = Contato(usuario_id=usuario_id, origem=origem, nome=dados.nome)
    aplicar_no_modelo(contato, ContatoCanonico(**dados.model_dump()))
    session.add(contato)
    await session.flush()
    return contato


async def atualizar(
    session: AsyncSession, contato: Contato, dados: ContatoUpdate
) -> Contato:
    atual = do_modelo(contato)
    patch = dados.model_dump(exclude_unset=True, exclude_none=True)
    # revalida pelo construtor (não `model_copy`): o patch traz e-mails/telefones
    # como dicts e eles precisam voltar a ser modelos antes da canonização.
    aplicar_no_modelo(contato, ContatoCanonico(**{**atual.model_dump(), **patch}))
    contato.updated_at = datetime.now(UTC)
    await session.flush()
    return contato


async def arquivar(session: AsyncSession, contato: Contato) -> None:
    """Soft delete. O sync leva a remoção aos provedores e o vínculo cai depois."""
    contato.arquivado = True
    contato.updated_at = datetime.now(UTC)
    await session.flush()


async def buscar_por_dedup(
    session: AsyncSession, chave: str | None
) -> Contato | None:
    if not chave:
        return None
    stmt = (
        select(Contato)
        .where(Contato.chave_dedup == chave, Contato.arquivado.is_(False))
        .order_by(Contato.created_at)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_canonico(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    canonico: ContatoCanonico,
    origem: str,
) -> tuple[Contato, bool]:
    """Casa por `chave_dedup` e MESCLA; se não casar, cria. Retorna (contato, criado).

    Mesclar (em vez de sobrescrever) é o que evita que uma importação apague o
    telefone que só existia na agenda do Hub.
    """
    dados = canonizar(canonico)
    existente = await buscar_por_dedup(session, dados.chave_dedup)
    if existente is not None:
        aplicar_no_modelo(existente, mesclar(do_modelo(existente), dados))
        existente.updated_at = datetime.now(UTC)
        await session.flush()
        return existente, False

    contato = Contato(usuario_id=usuario_id, origem=origem, nome=dados.nome)
    aplicar_no_modelo(contato, dados)
    session.add(contato)
    await session.flush()
    return contato, True


def exportar_vcf(contatos: list[Contato]) -> str:
    """Agenda → .vcf (rota sem credencial: importar no Google/Apple/Outlook na mão)."""
    return "".join(vcard.serializar(do_modelo(c), uid=str(c.id)) for c in contatos)


async def importar_vcf(
    session: AsyncSession, *, usuario_id: uuid.UUID, conteudo: str
) -> ImportacaoResultado:
    importados = atualizados = ignorados = 0
    for canonico in vcard.parsear(conteudo):
        canonico.origem = "vcard"
        if not calcular_chave_dedup(canonico):
            ignorados += 1  # cartão sem nome/e-mail/telefone: não dá para casar
            continue
        _, criado = await upsert_canonico(
            session, usuario_id=usuario_id, canonico=canonico, origem="vcard"
        )
        if criado:
            importados += 1
        else:
            atualizados += 1
    return ImportacaoResultado(
        importados=importados, atualizados=atualizados, ignorados=ignorados
    )
