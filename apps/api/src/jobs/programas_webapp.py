"""Coleta diária da Consulta de Programas do TransfereGov (§64).

Roda a consulta oficial com os filtros "Proposta Voluntária + ano corrente +
Apto a receber proposta: Sim" e grava em `programas` o que ela listou — é o
que faz a aba Oportunidades mostrar, NO MESMO DIA, o programa que o concedente
acabou de abrir, sem esperar o pacote de dados abertos.

Roda no processo do `worker` (refresh_diario agenda os loops). Best-effort:
falha vira `sync_runs` e log, nunca derruba o worker. Pausável pelo painel
(`services/fontes.CATALOGO_FONTES`, chave `programas_webapp`).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from ..connectors.programas_webapp import SOURCE_ID, Coleta, ProgramasWebappConnector
from ..db.session import SessionLocal, engine
from ..services import config as config_service
from ..services import fontes as fontes_service
from ..services import programas as programas_service

log = logging.getLogger(__name__)

HORA_UTC = int(os.getenv("PROGRAMAS_WEBAPP_HORA_UTC", "9"))
ATIVO = os.getenv("PROGRAMAS_WEBAPP_ATIVO", "1") not in ("0", "false", "False")
LOCK_ID = 8_140_233_904


async def _ano() -> int:
    """Ano da consulta: override do painel (`programas_webapp_ano`) ou o corrente."""
    valor = (await config_service.resolver("programas_webapp_ano") or "").strip()
    return int(valor) if valor.isdigit() else datetime.now().year


async def _registrar(inicio: datetime, status: str, registros: int, erro: str | None) -> None:
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO sync_runs "
                    "(id, fonte, tipo, status, registros, iniciado_em, finalizado_em, erro) "
                    "VALUES (gen_random_uuid(), :f, 'agendado', :s, :r, :i, now(), :e)"
                ),
                {
                    "f": SOURCE_ID,
                    "s": status,
                    "r": registros,
                    "i": inicio,
                    "e": erro[:2000] if erro else None,
                },
            )
    except Exception:  # noqa: BLE001 — contabilidade não desfaz a coleta
        log.warning("programas_webapp: não consegui anotar em sync_runs", exc_info=True)


async def executar(connector: ProgramasWebappConnector | None = None) -> dict:
    """Uma coleta completa. Devolve o resumo (log, rota admin e testes)."""
    if not await fontes_service.esta_ativa(SOURCE_ID):
        log.info("programas_webapp: fonte pausada no painel — pulando")
        return {"status": "pausada"}
    inicio = datetime.now(UTC)
    try:
        coleta = await (connector or ProgramasWebappConnector()).coletar(await _ano())
        assert isinstance(coleta, Coleta)
        async with SessionLocal() as s:
            gravados = await programas_service.upsert_do_webapp(s, coleta.programas)
            await s.commit()
        faltando = [f["chave"] for f in coleta.filtros if not f.get("ok")]
        # filtro que não casou = a lista pode incluir programa NÃO apto: é
        # coleta "degradada", e dizer isso em sync_runs é o que leva à calibração
        status = "degradado" if faltando else "ok"
        erro = f"filtros sem campo casado na página: {faltando}" if faltando else None
        await _registrar(inicio, status, len(coleta.programas), erro)
        resumo = {
            "status": status,
            "programas": len(coleta.programas),
            "paginas": coleta.paginas,
            "detalhes": coleta.detalhes,
            **gravados,
        }
        log.info("programas_webapp: %s", resumo)
        return resumo
    except Exception as exc:  # noqa: BLE001 — a falha vira registro, não silêncio
        log.exception("programas_webapp: coleta falhou")
        await _registrar(inicio, "erro", 0, f"{type(exc).__name__}: {exc}")
        return {"status": "erro", "erro": str(exc)}


async def sweep() -> dict:
    """`executar` sob advisory lock — o disparo manual e o agendado não somam browsers."""
    async with engine.connect() as conn:
        travou = (
            await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})
        ).scalar()
        if not travou:
            return {"status": "ocupado"}
        try:
            return await executar()
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})


def _segundos_ate_proxima_execucao(agora: datetime) -> float:
    alvo = agora.replace(hour=HORA_UTC, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def loop() -> None:
    if not ATIVO:
        log.warning("programas_webapp: desativado por PROGRAMAS_WEBAPP_ATIVO")
        return
    log.info("programas_webapp: agendado para %02d:00 UTC", HORA_UTC)
    while True:
        await asyncio.sleep(_segundos_ate_proxima_execucao(datetime.now(UTC)))
        try:
            await sweep()
        except Exception:  # noqa: BLE001 — o loop nunca morre
            log.exception("programas_webapp: rodada falhou")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(sweep() if os.getenv("RODAR_AGORA") == "1" else loop())
