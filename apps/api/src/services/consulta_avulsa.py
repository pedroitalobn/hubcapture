"""Consulta-avulsa (on-demand, cache-first).

Regra: toda leitura passa pelo cache. Só busca ao vivo em cache miss/stale.
Antes de retornar, garante `municipios_interesse(modo='avulso')` para o usuário
— senão o RLS esconderia do próprio usuário o resultado que ele acabou de buscar.

Além do cache de DADOS (`propostas.cache_atualizado_em`), existe um cache de
TENTATIVA por (fonte, município): o cache de dados só "existe" quando a coleta
trouxe linhas, então município sem registro numa fonte refazia a coleta INTEIRA
(CSV nacional, Chromium headless…) em toda carga do painel — e a API toda
pagava a conta. A tentativa recente (com ou sem resultado) vale como frescor.

Bookkeeping de `sync_runs` roda em sessão AUTÔNOMA: o request inteiro é uma
transação e um erro daria rollback, perdendo o registro do incidente. sync_runs
não tem RLS, então pode ser gravado por fora com commit próprio.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.base import get_connector
from ..core.config import settings
from ..db.session import SessionLocal
from ..ingestion.merge import merge_record
from ..jobs import curadoria as curadoria_job
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.proposta import Proposta
from ..models.sync_run import SyncRun
from . import fontes as fontes_service
from . import plano_gates
from . import propostas as propostas_service
from ._territorio import Municipios, ibges


async def _garantir_municipio_avulso(
    session: AsyncSession, usuario_id: uuid.UUID, ibge: str
) -> None:
    """Registra o município como 'avulso' para o usuário (idempotente)."""
    stmt = (
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    await session.execute(stmt)


async def _cache_fresco(session: AsyncSession, ibge: str, fonte: str) -> list[Proposta]:
    limite = datetime.now(UTC) - timedelta(seconds=settings.cache_ttl_seconds)
    stmt = select(Proposta).where(
        Proposta.municipio_ibge == ibge,
        Proposta.fonte == fonte,
        Proposta.cache_atualizado_em >= limite,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _registrar_sync(**kwargs) -> None:
    """Grava um SyncRun em transação própria (sobrevive a rollback do request)."""
    async with SessionLocal() as s:
        async with s.begin():
            s.add(SyncRun(**kwargs))


def _since() -> date:
    return date(date.today().year, 1, 1)


# ── Cache de tentativa de coleta ────────────────────────────────────────────
# (fonte, ibge) → (monotonic da última tentativa, sucesso?). Sucesso vale o TTL
# do cache-first; falha vale um TTL curto (a fonte pode voltar logo).
_TENTATIVAS: dict[tuple[str, str], tuple[float, bool]] = {}

# coletas simultâneas da busca ao vivo — cada uma pode levantar um Chromium ou
# parsear um CSV nacional; mais que isso disputa CPU em vez de ganhar tempo
_COLETAS_PARALELAS = 3


def limpar_cache_coleta() -> None:
    """Zera o cache de tentativa (testes/ops)."""
    _TENTATIVAS.clear()


def esquecer_municipio(ibge: str) -> None:
    """Esquece as tentativas de UM município (usado ao zerar o perfil).

    Sem isto, recomeçar do zero num município recém-coletado não recoletaria
    nada por até 6h — a tentativa recente conta como frescor e nenhuma fonte
    seria consultada, deixando o painel vazio como se as fontes não tivessem
    dados.
    """
    for chave in [c for c in _TENTATIVAS if c[1] == ibge]:
        del _TENTATIVAS[chave]


def _tentativa_fresca(fonte: str, ibge: str) -> bool:
    registro = _TENTATIVAS.get((fonte, ibge))
    if registro is None:
        return False
    momento, ok = registro
    ttl = settings.cache_ttl_seconds if ok else settings.coleta_erro_ttl_seconds
    return time.monotonic() - momento < ttl


def _marcar_tentativa(fonte: str, ibge: str, *, ok: bool) -> None:
    _TENTATIVAS[(fonte, ibge)] = (time.monotonic(), ok)


async def _coletar(fonte: str, ibge: str) -> list:
    """Coleta na fonte com teto de tempo (fonte pendurada não segura o request)."""
    connector = get_connector(fonte)
    return await asyncio.wait_for(
        connector.collect(ibge, since=_since()),
        timeout=settings.coleta_timeout_seconds,
    )


async def _ingerir(session: AsyncSession, registros: list) -> int:
    """Registros coletados → merge → upsert no cache canônico."""
    n = 0
    for record in registros:
        # aglutina API + scraping quando o connector trouxe os dois lados
        canonica = merge_record(record)
        await propostas_service.upsert(session, canonica)
        n += 1
    return n


async def consulta_avulsa(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio_ibge: str,
    fonte: str,
) -> list[Proposta]:
    # 0) o usuário precisa "ver" este município para o RLS devolver o resultado
    await _garantir_municipio_avulso(session, usuario_id, municipio_ibge)
    session.add(
        AuditLog(
            usuario_id=usuario_id,
            acao="consulta_avulsa",
            entidade=f"{fonte}:{municipio_ibge}",
        )
    )

    # 1) cache fresco? devolve na hora (nunca chama a fonte)
    frescas = await _cache_fresco(session, municipio_ibge, fonte)
    if frescas:
        return frescas

    # 1b) fonte consultada há pouco sem deixar linha p/ este município → serve
    # o cache (mesmo vazio) em vez de refazer a coleta cara
    if _tentativa_fresca(fonte, municipio_ibge):
        return await propostas_service.listar(session, municipio=municipio_ibge, fonte=fonte)

    # 2) miss/stale → fetch ao vivo
    iniciado = datetime.now(UTC)
    try:
        registros = await _coletar(fonte, municipio_ibge)
        n = await _ingerir(session, registros)
        # pílulas de categoria do que acabou de entrar: determinístico, sem rede
        # (o resumo por IA é outro pass, fora do request — jobs/curadoria).
        await curadoria_job.classificar_pendentes(session)
    except Exception as exc:  # nunca engolir: registra incidente e propaga
        _marcar_tentativa(fonte, municipio_ibge, ok=False)
        await _registrar_sync(
            usuario_id=usuario_id,
            fonte=fonte,
            tipo="avulso",
            status="erro",
            registros=0,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise

    _marcar_tentativa(fonte, municipio_ibge, ok=True)
    await _registrar_sync(
        usuario_id=usuario_id,
        fonte=fonte,
        tipo="avulso",
        status="ok",
        registros=n,
        iniciado_em=iniciado,
        finalizado_em=datetime.now(UTC),
    )

    # 3) devolve do cache (agora povoado), já sob o filtro de RLS
    return await propostas_service.listar(session, municipio=municipio_ibge, fonte=fonte)


# ── Busca em TEMPO REAL (multi-fonte) ───────────────────────────────────────
# A Captação filtra e a busca roda ao vivo: para cada município do perfil (ou o
# município filtrado) × fonte de captação relevante, reusa o fluxo cache-first
# acima (cache fresco responde na hora; stale/miss vai à fonte — API e/ou
# scraping via connector). Cada fonte é best-effort: falha vira status (e
# sync_run), nunca derruba a busca inteira.

# fontes cujo connector produz PROPOSTAS (captação). O recorte da v1 vive em
# `services/fontes.py` — hoje é a família TransfereGov (as APIs PostgREST, o CSV
# das discricionárias e o painel da Visão Geral).
CAPTACAO_FONTES: tuple[str, ...] = fontes_service.CAPTACAO


def _fontes_alvo(fonte: str | None, area: str | None, fontes_perfil: list[str] | None) -> list[str]:
    if fonte:
        return [fonte]
    if area:
        from .perfil import AREA_FONTES

        da_area = AREA_FONTES.get(area, set()) & set(CAPTACAO_FONTES)
        if da_area:
            return sorted(da_area)
    if fontes_perfil:
        do_perfil = set(fontes_perfil) & set(CAPTACAO_FONTES)
        if do_perfil:
            return sorted(do_perfil)
    return list(CAPTACAO_FONTES)


async def live_search(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio: Municipios = None,
    fonte: str | None = None,
    area: str | None = None,
    **filtros,
):
    """Coleta ao vivo nas fontes e devolve (página, total do recorte, status).

    A coleta é a parte cara (uma das fontes baixa um CSV de ~1 GB) — daí ela ser
    ação explícita no painel. A leitura sai paginada como a da listagem: quem
    acabou de atualizar quer ver a primeira página, não as milhares de linhas.

    As coletas rodam em PARALELO (com teto de simultaneidade) e FORA da sessão
    do request: o que precisa da sessão RLS — checar frescor e gravar o
    resultado — é rápido; o I/O externo, que é o demorado, não segura conexão
    de banco nem serializa fonte atrás de fonte.

    `municipio` é o recorte do painel: um código, vários (subconjunto do
    território escolhido na tela) ou nenhum — aí vale o território inteiro.
    """
    from ..models.preferencias import PreferenciasUsuario

    escolhidos = ibges(municipio)
    if escolhidos:
        alvos = escolhidos
    else:
        alvos = list(
            (
                await session.execute(
                    select(MunicipioInteresse.ibge).where(
                        MunicipioInteresse.usuario_id == usuario_id
                    )
                )
            )
            .scalars()
            .all()
        )
    pref = (
        await session.execute(
            select(PreferenciasUsuario).where(PreferenciasUsuario.usuario_id == usuario_id)
        )
    ).scalar_one_or_none()
    # o plano do usuário (§39) recorta as fontes da rodada — fonte fora da
    # assinatura não é consultada nem entra no status da coleta
    cfg_plano = await plano_gates.config_do_usuario(session, usuario_id)
    fontes = plano_gates.filtrar_fontes(
        cfg_plano, _fontes_alvo(fonte, area, list(pref.fontes or []) if pref else None)
    )

    # 1) sob a sessão RLS: visibilidade dos municípios + o que precisa coletar
    pares = [(ibge, f) for ibge in alvos for f in fontes]
    a_coletar: list[tuple[str, str]] = []
    for ibge in alvos:
        await _garantir_municipio_avulso(session, usuario_id, ibge)
    for ibge, f in pares:
        session.add(AuditLog(usuario_id=usuario_id, acao="consulta_avulsa", entidade=f"{f}:{ibge}"))
        if await _cache_fresco(session, ibge, f):
            continue
        if _tentativa_fresca(f, ibge):
            continue
        a_coletar.append((ibge, f))

    # 2) coletas em paralelo — só I/O externo, nenhuma conexão de banco envolvida
    semaforo = asyncio.Semaphore(_COLETAS_PARALELAS)

    async def _uma_coleta(par: tuple[str, str]):
        ibge, f = par
        inicio = datetime.now(UTC)
        try:
            async with semaforo:
                registros = await _coletar(f, ibge)
            return par, inicio, registros, None
        except Exception as exc:  # best-effort: vira status + sync_run
            return par, inicio, None, exc

    resultados = await asyncio.gather(*(_uma_coleta(p) for p in a_coletar))

    # 3) ingestão sequencial na sessão do request + bookkeeping
    erros: dict[tuple[str, str], str] = {}
    ingeriu = False
    for par, inicio, registros, exc in resultados:
        ibge, f = par
        n = 0
        if exc is None:
            try:
                n = await _ingerir(session, registros or [])
                ingeriu = ingeriu or n > 0
            except Exception as exc_ingestao:  # noqa: BLE001
                exc = exc_ingestao
        _marcar_tentativa(f, ibge, ok=exc is None)
        erro_txt = None if exc is None else f"{type(exc).__name__}: {exc}"[:2000]
        if exc is not None:
            erros[par] = type(exc).__name__
        await _registrar_sync(
            usuario_id=usuario_id,
            fonte=f,
            tipo="avulso",
            status="ok" if exc is None else "erro",
            registros=n,
            iniciado_em=inicio,
            finalizado_em=datetime.now(UTC),
            erro=erro_txt,
        )
    if ingeriu:
        # pílulas de categoria do que acabou de entrar (determinístico, sem rede)
        await curadoria_job.classificar_pendentes(session)

    status_fontes: list[dict] = []
    for ibge, f in pares:
        if (ibge, f) in erros:
            status_fontes.append(
                {"fonte": f, "municipio_ibge": ibge, "status": "erro", "erro": erros[(ibge, f)]}
            )
        else:
            status_fontes.append({"fonte": f, "municipio_ibge": ibge, "status": "ok"})

    rows, total = await propostas_service.listar_pagina(
        session, municipio=municipio, fonte=fonte, area=area, **filtros
    )
    return rows, total, status_fontes
