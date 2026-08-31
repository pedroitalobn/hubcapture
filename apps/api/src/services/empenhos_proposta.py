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
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors import pareceres_siconv
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
    """O que a rota de empenho aceita como filtro — `id_plano_acao` primeiro.

    O `id_externo` só serve de retaguarda para `id_plano_acao` quando é INTEIRO:
    nas propostas vindas do CSV do SIconv ele é o número formatado
    ("30011/2026"), e mandá-lo numa rota que espera um id inteiro devolve 422 —
    ou, pior, é ignorado e a resposta vem com empenho de todo mundo.
    """
    fonte_bruta = proposta.dados_fonte if isinstance(proposta.dados_fonte, dict) else {}
    plano = fonte_bruta.get("plano_acao")
    linha = plano if isinstance(plano, dict) else fonte_bruta
    externo = str(proposta.id_externo or "").strip()
    id_plano_acao = str(
        linha.get("id_plano_acao")
        or linha.get("numero_plano_acao")
        or (externo if externo.isdigit() else "")
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


async def totais_por_proposta(
    session: AsyncSession, propostas: Sequence[Proposta]
) -> dict[uuid.UUID, EmpenhoResumo]:
    """Totais dos DOCUMENTOS de empenho para VÁRIAS propostas, em uma consulta.

    O painel soma o agregado da execução financeira (`execucao.valor_empenhado`,
    do pacote/painel da fonte, ~mensal). Empenho recém-emitido só existe nas
    NOTAS — e a proposta que só tinha nota ficava fora do card "Empenhado",
    mesmo com o documento à vista na página dela. Aqui os documentos viram
    total por proposta para o resumo poder usá-los como retaguarda, com a mesma
    regra do detalhe (líquido das anulações).

    O casamento é o mesmo de `listar` (número da proposta OU do plano de ação),
    então um documento que case pelas duas chaves conta UMA vez por proposta.
    """
    por_numero: dict[str, set[uuid.UUID]] = {}
    por_plano: dict[str, set[uuid.UUID]] = {}
    for p in propostas:
        ch = chaves_da_proposta(p)
        if ch.get("numero_proposta"):
            por_numero.setdefault(ch["numero_proposta"], set()).add(p.id)
        if ch.get("id_plano_acao"):
            por_plano.setdefault(ch["id_plano_acao"], set()).add(p.id)
    if not por_numero and not por_plano:
        return {}

    condicoes = []
    if por_numero:
        condicoes.append(PropostaEmpenho.numero_proposta.in_(por_numero))
    if por_plano:
        condicoes.append(PropostaEmpenho.numero_plano_acao.in_(por_plano))

    rows = (await session.execute(select(PropostaEmpenho).where(or_(*condicoes)))).scalars().all()
    agrupado: dict[uuid.UUID, list[PropostaEmpenho]] = {}
    for e in rows:
        alvos = por_numero.get(e.numero_proposta or "", set()) | por_plano.get(
            e.numero_plano_acao or "", set()
        )
        for pid in alvos:
            agrupado.setdefault(pid, []).append(e)
    return {pid: resumir(itens) for pid, itens in agrupado.items()}


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

    # Cada universo tem sua fonte de empenho — mandar a chave errada para o
    # módulo errado era o que pintava "não consegui consultar" numa proposta
    # com empenho publicado:
    #   - discricionária/legal: o empenho vem do PACOTE DIÁRIO do SIconv
    #     (`jobs/siconv_diario`), já upsertado em `proposta_empenhos`. Não há
    #     rota on-demand pública; a resposta honesta é o cache da carga do dia.
    #   - fundo a fundo: o módulo `fundoafundo` publica `empenho` filtrável por
    #     `id_plano_acao` — mesma mecânica do especiais, só muda a base.
    #   - especiais: o caminho que já existia.
    if _e_siconv(proposta):
        return await _sync_siconv_webapp(session, proposta, chaves, usuario_id=usuario_id)

    iniciado = datetime.now(UTC)
    try:
        brutos = await _connector_de(proposta).collect_por_proposta(chaves)
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


BASE_FUNDO_A_FUNDO = "https://api.transferegov.gestao.gov.br/fundoafundo/"


async def _sync_siconv_webapp(
    session: AsyncSession,
    proposta: Proposta,
    chaves: dict[str, str],
    *,
    usuario_id: uuid.UUID | None = None,
) -> EmpenhoColeta:
    """Empenhos de proposta discricionária: pacote diário + listagem VIVA.

    O grosso vem do pacote do SIconv (`jobs/siconv_diario`, já em
    `proposta_empenhos`), mas o espelho público é ~mensal — empenho emitido
    depois do dump só aparece na listagem do webapp (acesso livre). Aqui a
    listagem é raspada e entra APENAS o número que o cache ainda não tem:
    sem esse filtro, o mesmo empenho apareceria duas vezes (uma por fonte)
    assim que o dump alcançasse o webapp.
    """
    id_siconv = str(proposta.id_externo or "").strip()
    if not id_siconv.isdigit():
        return EmpenhoColeta(status="ok", total=0, origem="carga diária do SIconv")

    iniciado = datetime.now(UTC)
    fonte_id = pareceres_siconv.SOURCE_ID_EMPENHO
    try:
        brutos = await pareceres_siconv.get_connector().empenhos_por_id_proposta(id_siconv)
    except Exception as exc:  # noqa: BLE001 — fonte de governo cai; o painel não
        erro = f"{type(exc).__name__}: {exc}"
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=fonte_id,
            tipo="avulso",
            status="erro",
            registros=0,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=erro[:1000],
        )
        # o cache do pacote continua valendo — a coleta viva é complementar
        return EmpenhoColeta(status="ok", total=0, origem="carga diária do SIconv")

    ja_no_cache = {
        (x.numero_empenho or "").strip() for x in await listar(session, proposta)
    }
    novos = [b for b in brutos if b.get("numero_empenho") not in ja_no_cache]
    canonicos = [
        normalize_empenho(
            b,
            fonte=fonte_id,
            numero_proposta=proposta.numero_proposta,
            numero_plano_acao=chaves.get("id_plano_acao"),
            municipio_ibge=proposta.municipio_ibge,
        )
        for b in novos
    ]
    if canonicos:
        await _upsert(session, canonicos)
    await registrar_sync(
        usuario_id=usuario_id,
        fonte=fonte_id,
        tipo="avulso",
        status="ok",
        registros=len(canonicos),
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
        erro=None,
    )
    return EmpenhoColeta(status="ok", total=len(canonicos), origem="fonte")


def _e_siconv(proposta: Proposta) -> bool:
    """Proposta do universo SIconv (discricionárias/legais)?"""
    if proposta.fonte in ("transferegov_disc", "transferegov_voluntarias"):
        return True
    dados = proposta.dados_fonte if isinstance(proposta.dados_fonte, dict) else {}
    return str(dados.get("_carga") or "").startswith("siconv")


def _connector_de(proposta: Proposta) -> EmpenhoEspecialConnector:
    """O connector de empenho apontado para o MÓDULO da proposta.

    O `EmpenhoEspecialConnector` já descobre a rota no spec de qualquer módulo
    PostgREST do TransfereGov — para o fundo a fundo basta trocar a base (a
    tabela lá se chama `empenho` e filtra por `id_plano_acao`, confirmado no
    spec do módulo).
    """
    if proposta.fonte == "transferegov_ff":
        return EmpenhoEspecialConnector(base_url=BASE_FUNDO_A_FUNDO)
    return EmpenhoEspecialConnector()


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
            if coleta.origem == "carga diária do SIconv" and itens:
                coleta.status = "ok"

    lidos = [EmpenhoRead.model_validate(x) for x in itens]
    lidos = await municipios_service.enriquecer(session, lidos)
    return lidos, resumir(lidos), coleta
