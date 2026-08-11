"""Empenhos da proposta — cache-first, com o TOTAL que a faixa de destaque usa.

Responde "o recurso saiu do papel?". A proposta sem empenho é promessa; com
empenho, é dinheiro reservado — e a diferença entre empenhado e pago é o
"disponibilizado e ainda não utilizado" que o gestor persegue (§28).

O agregado do painel da Visão Geral (`propostas.execucao.valor_empenhado`) só
existe quando aquela fonte publica. Aqui o total é SOMADO dos documentos, então
a tela tem o número mesmo quando o agregado não veio — que era exatamente o caso
em que o empenho não aparecia.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.empenhos_especiais import SOURCE_ID, EmpenhoEspecialConnector
from ..ingestion.normalizer_empenho import normalize_empenho
from ..models.proposta import Proposta
from ..models.proposta_empenho import PropostaEmpenho
from ..schemas.empenho import EmpenhoColeta, EmpenhoRead, EmpenhoResumo
from . import municipios as municipios_service
from ._sync import registrar_sync

# TTL do cache-first. Empenho novo aparece em dias, não em minutos.
TTL_HORAS = 12

_UPSERT_FIELDS = (
    "numero_proposta",
    "numero_plano_acao",
    "municipio_ibge",
    "numero_empenho",
    "data_empenho",
    "tipo_empenho",
    "situacao",
    "ano",
    "valor_empenhado",
    "valor_anulado",
    "valor_liquidado",
    "valor_pago",
    "ug_emitente",
    "gestao_emitente",
    "natureza_despesa",
    "fonte_recurso",
    "programa_trabalho",
    "observacao",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


def chaves_da_proposta(proposta: Proposta) -> dict[str, str]:
    """O que a rota de empenho aceita como filtro — o nº da proposta primeiro."""
    fonte_bruta = proposta.dados_fonte if isinstance(proposta.dados_fonte, dict) else {}
    plano = fonte_bruta.get("plano_acao")
    linha = plano if isinstance(plano, dict) else fonte_bruta
    id_plano_acao = str(
        linha.get("id_plano_acao") or linha.get("numero_plano_acao") or proposta.id_externo or ""
    ).strip()
    numero = (proposta.numero_proposta or "").strip()

    chaves = {
        "numero_proposta": numero,
        "id_proposta": numero,
        "id_plano_acao": id_plano_acao,
        "numero_plano_acao": id_plano_acao,
        "id_plano_trabalho": (proposta.numero_plano_trabalho or "").strip(),
    }
    return {k: v for k, v in chaves.items() if v}


async def listar(session: AsyncSession, proposta: Proposta) -> list[PropostaEmpenho]:
    chaves = chaves_da_proposta(proposta)
    condicoes = []
    if chaves.get("numero_proposta"):
        condicoes.append(PropostaEmpenho.numero_proposta == chaves["numero_proposta"])
    if chaves.get("id_plano_acao"):
        condicoes.append(PropostaEmpenho.numero_plano_acao == chaves["id_plano_acao"])
    if not condicoes:
        return []

    stmt = (
        select(PropostaEmpenho)
        .where(or_(*condicoes))
        .order_by(
            PropostaEmpenho.data_empenho.desc().nullslast(),
            PropostaEmpenho.numero_empenho.desc().nullslast(),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


def resumir(itens: list[EmpenhoRead] | list[PropostaEmpenho]) -> EmpenhoResumo:
    """Totais da proposta. O empenhado sai LÍQUIDO das anulações — empenho
    anulado que continuasse somando diria que há recurso onde não há."""
    zero = Decimal("0")

    def soma(campo: str) -> Decimal:
        return sum((getattr(x, campo, None) or zero for x in itens), zero)

    empenhado = soma("valor_empenhado") - soma("valor_anulado")
    pago = soma("valor_pago")
    datas = sorted(x.data_empenho for x in itens if x.data_empenho)
    return EmpenhoResumo(
        total=len(itens),
        valor_empenhado=max(empenhado, zero),
        valor_anulado=soma("valor_anulado"),
        valor_liquidado=soma("valor_liquidado"),
        valor_pago=pago,
        valor_a_utilizar=max(empenhado - pago, zero),
        primeiro_empenho=datas[0] if datas else None,
        ultimo_empenho=datas[-1] if datas else None,
    )


async def _upsert(session: AsyncSession, canonicos: list) -> None:
    now = datetime.now(UTC)
    for c in canonicos:
        values = c.model_dump()
        values["cache_atualizado_em"] = now
        stmt = pg_insert(PropostaEmpenho).values(**values)
        update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
        update_set["cache_atualizado_em"] = now
        update_set["updated_at"] = now
        stmt = stmt.on_conflict_do_update(
            constraint="uq_proposta_empenhos_fonte_id_externo", set_=update_set
        )
        await session.execute(stmt)


def _esta_fresco(itens: list[PropostaEmpenho]) -> bool:
    if not itens:
        return False
    limite = datetime.now(UTC) - timedelta(hours=TTL_HORAS)
    return all(x.cache_atualizado_em and x.cache_atualizado_em >= limite for x in itens)


async def sync_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    usuario_id: uuid.UUID | None = None,
) -> EmpenhoColeta:
    """Coleta na fonte e grava. Falha vira status + `sync_runs`, nunca 500."""
    chaves = chaves_da_proposta(proposta)
    if not chaves:
        return EmpenhoColeta(status="sem_chave", total=0)

    iniciado = datetime.now(UTC)
    try:
        brutos = await EmpenhoEspecialConnector().collect_por_proposta(chaves)
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
        return EmpenhoColeta(status="erro", total=0, erro=erro[:500])

    canonicos = [
        normalize_empenho(
            b,
            fonte=SOURCE_ID,
            numero_proposta=proposta.numero_proposta,
            numero_plano_acao=chaves.get("id_plano_acao"),
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
        status="ok",
        registros=len(canonicos),
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
        erro=None,
    )
    return EmpenhoColeta(status="ok", total=len(canonicos), origem="fonte")


async def por_proposta(
    session: AsyncSession,
    proposta: Proposta,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
) -> tuple[list[EmpenhoRead], EmpenhoResumo, EmpenhoColeta]:
    """Cache-first: cache na hora; fonte quando stale/vazio ou sob pedido."""
    itens = await listar(session, proposta)
    coleta = EmpenhoColeta(status="ok", total=len(itens), origem="cache")

    if atualizar or not _esta_fresco(itens):
        coleta = await sync_proposta(session, proposta, usuario_id=usuario_id)
        if coleta.status != "erro":
            itens = await listar(session, proposta)
            coleta.total = len(itens)

    lidos = [EmpenhoRead.model_validate(x) for x in itens]
    lidos = await municipios_service.enriquecer(session, lidos)
    return lidos, resumir(lidos), coleta
