"""Pareceres do plano de trabalho — cache-first, consultável pelo número do plano.

A pergunta que este serviço responde é a do gestor: "quais pareceres saíram no
plano de trabalho X?". A proposta é só o caminho mais comum até esse número
(`propostas.numero_plano_trabalho`); quem já tem o número consulta direto.

Cache-first como todo o resto (§10): responde do banco na hora; só vai à fonte
quando o cache está velho/vazio ou o chamador pede atualização. Falha de fonte
vira `sync_runs` + status na resposta — nunca 500 e nunca silêncio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors import planos_trabalho
from ..connectors.pareceres import SOURCE_ID, ParecerConnector
from ..ingestion._campos import palavras
from ..ingestion.normalizer_parecer import normalize_parecer
from ..models.parecer import Parecer
from ..models.proposta import Proposta
from ..schemas.parecer import ParecerColeta, ParecerRead
from . import municipios as municipios_service
from ._sync import registrar_sync

# TTL do cache-first. Tramitação muda em dias, não em minutos.
TTL_HORAS = 12

_UPSERT_FIELDS = (
    "numero_plano_trabalho",
    "numero_proposta",
    "municipio_ibge",
    "data_parecer",
    "esfera",
    "responsavel",
    "papel",
    "cargo",
    "situacao",
    "texto",
    "url_parecer",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


async def listar(session: AsyncSession, numero_plano_trabalho: str) -> list[Parecer]:
    """Pareceres do plano, do mais recente para o mais antigo (o RLS recorta)."""
    stmt = (
        select(Parecer)
        .where(Parecer.numero_plano_trabalho == str(numero_plano_trabalho).strip())
        .order_by(Parecer.data_parecer.desc().nullslast(), Parecer.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


def _esta_fresco(itens: list[Parecer]) -> bool:
    if not itens:
        return False
    limite = datetime.now(UTC) - timedelta(hours=TTL_HORAS)
    return all(p.cache_atualizado_em and p.cache_atualizado_em >= limite for p in itens)


async def _upsert(session: AsyncSession, canonicos: list) -> None:
    now = datetime.now(UTC)
    for c in canonicos:
        values = c.model_dump()
        values["cache_atualizado_em"] = now
        stmt = pg_insert(Parecer).values(**values)
        update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
        update_set["cache_atualizado_em"] = now
        update_set["updated_at"] = now
        stmt = stmt.on_conflict_do_update(
            constraint="uq_pareceres_fonte_id_externo", set_=update_set
        )
        await session.execute(stmt)


async def sync_plano(
    session: AsyncSession,
    numero_plano_trabalho: str,
    *,
    numero_proposta: str | None = None,
    municipio_ibge: str | None = None,
    usuario_id: uuid.UUID | None = None,
) -> ParecerColeta:
    """Coleta na fonte e grava. Best-effort: falha vira status + `sync_runs`."""
    numero_plano = str(numero_plano_trabalho).strip()
    iniciado = datetime.now(UTC)
    connector = ParecerConnector()
    try:
        brutos = await connector.collect_por_plano(numero_plano)
    except Exception as exc:
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=SOURCE_ID,
            tipo="avulso",
            status="erro",
            registros=0,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=str(exc)[:1000],
        )
        return ParecerColeta(
            numero_plano_trabalho=numero_plano, status="erro", total=0, erro=str(exc)[:500]
        )

    canonicos = [
        normalize_parecer(
            b,
            numero_plano_trabalho=numero_plano,
            fonte=SOURCE_ID,
            numero_proposta=numero_proposta,
            municipio_ibge=municipio_ibge,
        )
        for b in brutos
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
    return ParecerColeta(numero_plano_trabalho=numero_plano, status="ok", total=len(canonicos))


async def por_plano(
    session: AsyncSession,
    numero_plano_trabalho: str,
    *,
    atualizar: bool = False,
    numero_proposta: str | None = None,
    municipio_ibge: str | None = None,
    usuario_id: uuid.UUID | None = None,
) -> tuple[list[ParecerRead], ParecerColeta]:
    """Cache-first: devolve o que está no banco; busca na fonte se stale/vazio."""
    numero_plano = str(numero_plano_trabalho or "").strip()
    if not numero_plano:
        return [], ParecerColeta(status="sem_plano_trabalho", total=0)

    itens = await listar(session, numero_plano)
    coleta = ParecerColeta(numero_plano_trabalho=numero_plano, status="ok", total=len(itens))

    if atualizar or not _esta_fresco(itens):
        coleta = await sync_plano(
            session,
            numero_plano,
            numero_proposta=numero_proposta,
            municipio_ibge=municipio_ibge,
            usuario_id=usuario_id,
        )
        if coleta.status == "ok":
            itens = await listar(session, numero_plano)
        coleta.total = len(itens)

    lidos = [ParecerRead.model_validate(p) for p in itens]
    return await municipios_service.enriquecer(session, lidos), coleta


async def resolver_plano_trabalho(session: AsyncSession, proposta: Proposta) -> str | None:
    """O id do plano de trabalho desta proposta — a chave que a fonte exige.

    A rota de análises filtra pelo id INTEIRO do plano (§36). A proposta que
    chega pelo CSV do SIconv não traz esse id, e o fallback antigo mandava o
    NÚMERO DA PROPOSTA ("30011/2026"): o connector recusava, e o painel dizia
    "não consegui consultar os pareceres" numa proposta que tem parecer
    publicado na fonte. A ordem aqui é a do custo:

      1. o que já está na coluna, se for id;
      2. o registro-fonte da coleta (sem rede, e corrige o que já está no cache);
      3. a rota de planos de trabalho do módulo especiais;
      4. o número da proposta, como último recurso — a fonte às vezes o aceita,
         e é melhor tentar do que devolver vazio sem explicar.

    Quando descobre um id novo, GRAVA na proposta: a próxima consulta (e o
    andamento, e o espelho) já nascem com o elo.
    """
    guardado = str(proposta.numero_plano_trabalho or "").strip()
    if guardado.isdigit():
        return guardado

    do_registro = planos_trabalho.id_no_registro_fonte(proposta.dados_fonte)
    if not do_registro:
        do_registro = await planos_trabalho.get_connector().id_por_proposta(
            {
                "id_proposta": _id_proposta_de(proposta),
                "numero_proposta": proposta.numero_proposta,
                "id_plano_acao": proposta.id_externo,
                "numero_plano_acao": proposta.numero_proposta,
            }
        )

    if do_registro:
        if do_registro != guardado:
            await session.execute(
                update(Proposta)
                .where(Proposta.id == proposta.id)
                .values(numero_plano_trabalho=do_registro)
            )
            proposta.numero_plano_trabalho = do_registro
        return do_registro

    return guardado or (proposta.numero_proposta or None)


def _id_proposta_de(proposta: Proposta) -> str | None:
    """`ID_PROPOSTA` do registro-fonte (o id interno do SIconv), se houver."""
    return por_termos_no_registro(proposta.dados_fonte, ("id", "proposta"))


def por_termos_no_registro(dados, termos: tuple[str, ...]) -> str | None:
    """Primeiro valor do registro-fonte cuja chave tenha todas as palavras."""
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if isinstance(chave, str) and isinstance(valor, (str, int)):
                if palavras(chave).issuperset(termos):
                    bruto = str(valor).strip()
                    if bruto:
                        return bruto
        for valor in dados.values():
            achado = por_termos_no_registro(valor, termos)
            if achado:
                return achado
    elif isinstance(dados, list):
        for item in dados:
            achado = por_termos_no_registro(item, termos)
            if achado:
                return achado
    return None


async def por_proposta(
    session: AsyncSession,
    proposta_id: uuid.UUID,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
) -> tuple[list[ParecerRead], ParecerColeta]:
    """Caminho do painel: da proposta ao plano de trabalho, e daí aos pareceres."""
    proposta = (
        await session.execute(select(Proposta).where(Proposta.id == proposta_id))
    ).scalar_one_or_none()
    if proposta is None:
        return [], ParecerColeta(status="sem_plano_trabalho", total=0)

    numero_plano = await resolver_plano_trabalho(session, proposta)
    if not numero_plano:
        return [], ParecerColeta(status="sem_plano_trabalho", total=0)

    return await por_plano(
        session,
        numero_plano,
        atualizar=atualizar,
        numero_proposta=proposta.numero_proposta,
        municipio_ibge=proposta.municipio_ibge,
        usuario_id=usuario_id,
    )
