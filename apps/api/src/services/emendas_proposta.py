"""Emendas (e parlamentares autores) da proposta — cache-first.

Responde "de quem é o dinheiro desta proposta?". A pergunta é da CAPTAÇÃO: qual
emenda banca o plano de ação e quem a assinou — é com esse gabinete que o gestor
negocia. Não confundir com a lente de emendas dos repasses (§26b), que é sobre
dinheiro já pago.

Cache-first como todo o resto (§10). Quando a rota do módulo não está calibrada
ou a fonte cai, ainda respondemos com o que o REGISTRO-FONTE do plano de ação já
carrega (parlamentar + valor do repasse) — degradação com conteúdo, não seção
vazia. A resposta diz de onde veio (`coleta.origem`), porque "a fonte não
respondeu" e "esta proposta não tem emenda" não podem virar a mesma tela.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.emendas_especiais import (
    SOURCE_ID,
    EmendaEspecialConnector,
    emendas_do_registro_fonte,
)
from ..ingestion.normalizer_emenda import normalize_emenda
from ..models.proposta import Proposta
from ..models.proposta_emenda import PropostaEmenda
from ..schemas.emenda import EmendaColeta, EmendaRead
from . import municipios as municipios_service
from ._sync import registrar_sync

# TTL do cache-first. Autoria de emenda não muda de hora em hora.
TTL_HORAS = 24

_UPSERT_FIELDS = (
    "numero_plano_acao",
    "numero_proposta",
    "municipio_ibge",
    "codigo_emenda",
    "numero_emenda",
    "ano",
    "tipo_emenda",
    "parlamentar",
    "partido",
    "uf_parlamentar",
    "cargo_parlamentar",
    "codigo_parlamentar",
    "valor",
    "valor_empenhado",
    "valor_pago",
    "funcao",
    "situacao",
    "url_origem",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


def chaves_da_proposta(proposta: Proposta) -> dict[str, str]:
    """O que sabemos da proposta que a fonte aceita como filtro.

    No módulo especiais o `id_externo` da proposta É o id do plano de ação — é
    por ele que a rota da emenda filtra. O nº da proposta e o do plano de
    trabalho entram como retaguarda (rotas diferentes filtram por chaves
    diferentes; a descoberta escolhe qual usar).
    """
    fonte_bruta = proposta.dados_fonte if isinstance(proposta.dados_fonte, dict) else {}
    plano = fonte_bruta.get("plano_acao")
    linha = plano if isinstance(plano, dict) else fonte_bruta

    id_plano_acao = str(
        linha.get("id_plano_acao") or linha.get("numero_plano_acao") or proposta.id_externo or ""
    ).strip()

    chaves = {
        "id_plano_acao": id_plano_acao,
        "numero_plano_acao": id_plano_acao,
        "numero_proposta": (proposta.numero_proposta or "").strip(),
        "id_proposta": (proposta.numero_proposta or "").strip(),
        "numero_plano_trabalho": (proposta.numero_plano_trabalho or "").strip(),
        "id_plano_trabalho": (proposta.numero_plano_trabalho or "").strip(),
    }
    return {k: v for k, v in chaves.items() if v}


async def listar(session: AsyncSession, proposta: Proposta) -> list[PropostaEmenda]:
    """Emendas ligadas à proposta por qualquer um dos elos que temos."""
    chaves = chaves_da_proposta(proposta)
    condicoes = []
    if chaves.get("id_plano_acao"):
        condicoes.append(PropostaEmenda.numero_plano_acao == chaves["id_plano_acao"])
    if chaves.get("numero_proposta"):
        condicoes.append(PropostaEmenda.numero_proposta == chaves["numero_proposta"])
    if not condicoes:
        return []

    stmt = (
        select(PropostaEmenda)
        .where(or_(*condicoes))
        .order_by(
            PropostaEmenda.ano.desc().nullslast(),
            PropostaEmenda.parlamentar.asc().nullslast(),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


def _esta_fresco(itens: list[PropostaEmenda]) -> bool:
    if not itens:
        return False
    limite = datetime.now(UTC) - timedelta(hours=TTL_HORAS)
    return all(x.cache_atualizado_em and x.cache_atualizado_em >= limite for x in itens)


async def _upsert(session: AsyncSession, canonicos: list) -> None:
    now = datetime.now(UTC)
    for c in canonicos:
        values = c.model_dump()
        values["cache_atualizado_em"] = now
        stmt = pg_insert(PropostaEmenda).values(**values)
        update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
        update_set["cache_atualizado_em"] = now
        update_set["updated_at"] = now
        stmt = stmt.on_conflict_do_update(
            constraint="uq_proposta_emendas_fonte_id_externo", set_=update_set
        )
        await session.execute(stmt)


async def sync_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    usuario_id: uuid.UUID | None = None,
) -> EmendaColeta:
    """Coleta na fonte e grava. Best-effort: falha vira status + `sync_runs`,
    com retaguarda no registro-fonte (que não depende da rede)."""
    chaves = chaves_da_proposta(proposta)
    if not chaves:
        return EmendaColeta(status="sem_chave", total=0)

    iniciado = datetime.now(UTC)
    origem = "fonte"
    erro: str | None = None
    try:
        brutos = await EmendaEspecialConnector().collect_por_proposta(chaves)
    except Exception as exc:  # noqa: BLE001 — fonte de governo cai; o painel não
        erro = f"{type(exc).__name__}: {exc}"
        brutos = []

    if not brutos:
        # o plano de ação já traz o parlamentar da emenda — melhor que nada e
        # não custa rede
        brutos = emendas_do_registro_fonte(proposta.dados_fonte)
        origem = "registro_fonte" if brutos else origem

    canonicos = [
        normalize_emenda(
            b,
            fonte=SOURCE_ID,
            numero_plano_acao=chaves.get("id_plano_acao"),
            numero_proposta=proposta.numero_proposta,
            municipio_ibge=proposta.municipio_ibge,
        )
        for b in brutos
    ]
    if canonicos:
        await _upsert(session, canonicos)

    await registrar_sync(
        usuario_id=usuario_id,
        fonte=SOURCE_ID,
        tipo="avulso",
        status="erro" if (erro and not canonicos) else ("degradado" if erro else "ok"),
        registros=len(canonicos),
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
        erro=erro[:1000] if erro else None,
    )

    if erro and not canonicos:
        return EmendaColeta(status="erro", total=0, erro=erro[:500])
    return EmendaColeta(
        status="ok", total=len(canonicos), origem=origem, erro=erro[:500] if erro else None
    )


async def por_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
) -> tuple[list[EmendaRead], EmendaColeta]:
    """Cache-first: devolve o que está no banco; consulta a fonte se stale/vazio."""
    itens = await listar(session, proposta)
    coleta = EmendaColeta(status="ok", total=len(itens), origem="cache")

    if atualizar or not _esta_fresco(itens):
        coleta = await sync_proposta(session, proposta, usuario_id=usuario_id)
        if coleta.status != "erro":
            itens = await listar(session, proposta)
            coleta.total = len(itens)

    lidos = [EmendaRead.model_validate(x) for x in itens]
    return await municipios_service.enriquecer(session, lidos), coleta
