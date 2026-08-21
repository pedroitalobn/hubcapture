"""Pacote de dados abertos do SIconv — catálogo, download e carga (admin).

As transferências **discricionárias e legais** não têm rota de consulta por
município: o TransfereGov publica a base inteira em
`https://api-publica.transferegov.gestao.gov.br/downloads/…`, um ZIP por TABELA
do modelo (proposta, emenda, convenio, empenho…). Quem quer TODAS as propostas
de um município não tem outro caminho senão baixar o pacote e recortar aqui.

Estas rotas são a porta de operação disso:

* `GET /admin/siconv/files` — o catálogo com o estado REAL de cada arquivo
  (existe? que nome respondeu? quanto pesa?), sondado ao vivo sem baixar nada,
  mais o histórico das últimas cargas. É onde se descobre que a fonte renomeou
  um arquivo — antes de a carga da madrugada falhar.
* `POST /admin/siconv/load` — dispara a carga (baixa → descompacta → COPY →
  upsert), opcionalmente só de algumas tabelas.
* `GET /admin/siconv/runs` — as últimas execuções (`sync_runs`).

O download em si NÃO é proxiado por aqui: `url` no catálogo é o link direto da
fonte, e são centenas de MB por arquivo — passá-los pela API seria pagar banda
duas vezes para entregar o que o navegador baixa melhor sozinho.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors import siconv_downloads
from ...core.users import current_superuser
from ...jobs import siconv_diario
from ...models.usuario import Usuario
from ...schemas.siconv import (
    ArquivoSiconv,
    CargaIniciada,
    CargaSiconv,
    CatalogoSiconv,
    PedidoCarga,
)
from ..deps import get_plataforma_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/siconv", tags=["admin"])

LIMITE_RUNS = 10


async def _ultimas_cargas(session: AsyncSession, limite: int) -> list[CargaSiconv]:
    linhas = await session.execute(
        text(
            "SELECT status, registros, iniciado_em, finalizado_em, erro FROM sync_runs "
            "WHERE fonte = :f ORDER BY iniciado_em DESC NULLS LAST LIMIT :n"
        ),
        {"f": siconv_diario.FONTE, "n": limite},
    )
    return [
        CargaSiconv(
            status=linha.status or "?",
            registros=int(linha.registros or 0),
            iniciado_em=linha.iniciado_em,
            finalizado_em=linha.finalizado_em,
            erro=linha.erro,
        )
        for linha in linhas
    ]


@router.get("/files", response_model=CatalogoSiconv)
async def listar_arquivos(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_plataforma_db),
) -> CatalogoSiconv:
    """Catálogo do pacote com disponibilidade ao vivo (uma sondagem por tabela).

    Sonda com HEAD (e um GET de 1 byte quando o CDN recusa HEAD): confirma que o
    arquivo existe e quanto pesa sem baixar nada. Arquivo indisponível vem com o
    `erro` em vez de sumir da lista — "a fonte renomeou" e "a fonte caiu"
    precisam ser distinguíveis na tela.
    """
    disponibilidades, monitorados, cargas = await asyncio.gather(
        siconv_downloads.inspecionar_todos(),
        session.scalar(
            text("SELECT count(DISTINCT ibge) FROM municipios_interesse WHERE ibge IS NOT NULL")
        ),
        _ultimas_cargas(session, LIMITE_RUNS),
    )

    return CatalogoSiconv(
        base_url=await siconv_downloads.base_url(),
        escopo_propostas=await siconv_diario.escopo_propostas(),
        municipios_monitorados=int(monitorados or 0),
        tabelas_da_carga=list(siconv_diario.tabelas_alvo()),
        arquivos=[ArquivoSiconv(**vars(d)) for d in disponibilidades],
        ultimas_cargas=cargas,
    )


@router.get("/runs", response_model=list[CargaSiconv])
async def listar_cargas(
    limite: int = LIMITE_RUNS,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_plataforma_db),
) -> list[CargaSiconv]:
    return await _ultimas_cargas(session, max(1, min(limite, 100)))


@router.post("/load", response_model=CargaIniciada, status_code=202)
async def disparar_carga(
    pedido: PedidoCarga | None = None,
    _admin: Usuario = Depends(current_superuser),
) -> CargaIniciada:
    """Dispara a carga AGORA, sem esperar a janela agendada.

    `asyncio.create_task` e nunca `BackgroundTasks` (§19b): a carga leva minutos
    e o `BackgroundTasks` roda antes do teardown da sessão do request, prendendo
    a conexão. O trabalho pesado é I/O (download em streaming para disco) e
    depois `COPY`/upsert — quem sua é o Postgres, não este processo.

    A trava é o advisory lock do próprio `sweep`: dois disparos (ou um disparo
    e o worker agendado) não carregam a mesma tabela em paralelo — o segundo
    responde "ocupado" no log e sai.
    """
    pedidas = list(dict.fromkeys(pedido.tabelas if pedido else []))
    desconhecidas = [t for t in pedidas if t not in siconv_downloads.ARQUIVOS]
    if desconhecidas:
        raise HTTPException(
            422,
            detail=(
                f"tabela fora do catálogo do SIconv: {', '.join(desconhecidas)}. "
                f"Disponíveis: {', '.join(sorted(siconv_downloads.ARQUIVOS))}"
            ),
        )

    alvo = tuple(pedidas) or siconv_diario.tabelas_alvo()

    async def _rodar() -> None:
        try:
            await siconv_diario.sweep(tabelas=alvo)
        except Exception:  # noqa: BLE001 — a task é órfã: o erro só existe no log
            log.exception("siconv: carga disparada pelo admin falhou")

    asyncio.create_task(_rodar())
    return CargaIniciada(
        iniciada=True,
        tabelas=list(alvo),
        detalhe=(
            "carga iniciada em segundo plano — acompanhe em GET /admin/siconv/runs "
            "(são centenas de MB por arquivo; leva minutos)"
        ),
    )
