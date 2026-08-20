"""Refresh diário do banco — mantém as propostas frescas sem coleta no request.

POR QUE EXISTE: até aqui os dados só ficavam atualizados porque TODA abertura do
painel de Captação disparava `live-search`, que coleta das fontes ao vivo e só
então lê do banco. Isso custava o download do CSV (~1 GB) do `transferegov_disc`
a cada visita e era a causa do delay. Ao passar o painel a ler do banco
paginado, some o único mecanismo que alimentava a base — sem este job o banco
CONGELA. Por isso ele entra ANTES da mudança da tela.

Roda como processo próprio (serviço `worker` no compose), não dentro da API: o
sweep leva minutos e não pode competir com o event loop que atende request.

Best-effort por usuário, no mesmo espírito do primeiro_sync: uma fonte fora do
ar registra o incidente em `sync_runs` (feito pelos serviços chamados) e não
derruba o resto do sweep.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, select, text

from ..db.session import SessionLocal, engine
from ..models.municipio_interesse import MunicipioInteresse
from ..models.preferencias import PreferenciasUsuario
from ..services import primeiro_sync

log = logging.getLogger(__name__)

# Hora (UTC) do sweep. 06:00 UTC ≈ 03:00 em Brasília — fora do horário de uso.
HORA_UTC = int(os.getenv("REFRESH_DIARIO_HORA_UTC", "6"))
ATIVO = os.getenv("REFRESH_DIARIO_ATIVO", "1") not in ("0", "false", "False")
# Pausa entre usuários: evita martelar as fontes oficiais em rajada (e tomar
# rate limit / bloqueio), que derrubaria o sweep inteiro em vez de um usuário.
PAUSA_ENTRE_USUARIOS_S = float(os.getenv("REFRESH_DIARIO_PAUSA_S", "2"))

# Trava global do sweep. Sem ela, duas réplicas do worker (ou um deploy com o
# container antigo ainda de pé) coletariam em paralelo e disputariam o upsert
# das MESMAS linhas. A advisory lock é por sessão: cai sozinha se o processo
# morrer, sem deixar trava órfã como faria uma flag em tabela.
LOCK_ID = 8_140_233_901  # arbitrário e fixo — só precisa não colidir


async def _usuarios_para_sincronizar() -> list[tuple]:
    """(usuario_id, municipios, fontes, areas) de quem tem território definido.

    Varre TODOS os usuários com município de interesse — ninguém deve abrir o
    painel e encontrar dado velho. Se o custo do sweep crescer demais com a
    base, o recorte por atividade recente é o próximo passo, mas ele defasa
    justamente quem volta depois de um tempo.
    """
    # Sessão SEM tenant de propósito: o sweep precisa enxergar todos os
    # usuários pra saber a quem sincronizar. A coleta em si roda por usuário,
    # dentro de rls_session (no primeiro_sync.executar), então o RLS segue
    # valendo para tudo que grava dado de território.
    async with SessionLocal() as s:
        ids = (await s.execute(select(distinct(MunicipioInteresse.usuario_id)))).scalars().all()
        saida = []
        for uid in ids:
            municipios = (
                (
                    await s.execute(
                        select(MunicipioInteresse.ibge).where(MunicipioInteresse.usuario_id == uid)
                    )
                )
                .scalars()
                .all()
            )
            pref = (
                await s.execute(
                    select(PreferenciasUsuario).where(PreferenciasUsuario.usuario_id == uid)
                )
            ).scalar_one_or_none()
            if not municipios:
                continue
            saida.append(
                (
                    uid,
                    list(municipios),
                    list(pref.fontes or []) if pref else [],
                    list(pref.areas or []) if pref else [],
                )
            )
        return saida


async def sweep() -> dict:
    """Uma passada completa. Devolve o resumo (usado no log e nos testes)."""
    inicio = datetime.now(UTC)
    # Conexão dedicada: a advisory lock vive enquanto ESTA conexão existir.
    async with engine.connect() as conn:
        travou = (
            await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})
        ).scalar()
        if not travou:
            log.warning("refresh diário: outro sweep em andamento — pulando")
            return {"status": "ocupado", "usuarios": 0}

        try:
            alvos = await _usuarios_para_sincronizar()
            log.info("refresh diário: %d usuário(s) no sweep", len(alvos))
            ok = falhas = 0
            for usuario_id, municipios, fontes, areas in alvos:
                try:
                    # Reusa o MESMO caminho do 1º sync: cobre as 4 dimensões e
                    # grava pelo upsert (fonte, id_externo), que preserva o id
                    # da proposta — favoritos e pastas continuam apontando certo.
                    await primeiro_sync.executar(usuario_id, municipios, fontes, areas)
                    ok += 1
                except Exception:
                    falhas += 1
                    log.warning("refresh diário: usuário %s falhou", usuario_id, exc_info=True)
                await asyncio.sleep(PAUSA_ENTRE_USUARIOS_S)

            dur = (datetime.now(UTC) - inicio).total_seconds()
            log.info("refresh diário: concluído — %d ok, %d falha(s), %.0fs", ok, falhas, dur)
            return {"status": "ok", "usuarios": len(alvos), "ok": ok, "falhas": falhas}
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})


def _segundos_ate_proxima_execucao(agora: datetime) -> float:
    """Segundos até o próximo HORA_UTC:00. Sempre no futuro (nunca 0/negativo,
    que faria o loop girar em falso e repetir o sweep várias vezes na mesma hora)."""
    alvo = agora.replace(hour=HORA_UTC, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def loop() -> None:
    if not ATIVO:
        log.warning("refresh diário: desativado por REFRESH_DIARIO_ATIVO")
        return
    log.info("refresh diário: agendado para %02d:00 UTC", HORA_UTC)
    while True:
        espera = _segundos_ate_proxima_execucao(datetime.now(UTC))
        log.info("refresh diário: próximo sweep em %.0f min", espera / 60)
        await asyncio.sleep(espera)
        try:
            await sweep()
        except Exception:
            # Nunca deixa o loop morrer: uma falha do sweep não pode encerrar o
            # agendador e congelar o banco até alguém reiniciar o container.
            log.exception("refresh diário: sweep falhou")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # RODAR_AGORA=1 força um sweep imediato e sai — usado para testar o job e
    # para primeira carga, sem esperar a janela agendada.
    if os.getenv("RODAR_AGORA") == "1":
        asyncio.run(sweep())
    else:
        # O worker é UM processo para os dois relógios diários: o refresh das
        # propostas (06:00) e o enriquecimento de pareceres/empenhos (08:00,
        # `enriquecimento_diario`). Um container a mais só para o segundo
        # relógio custaria memória que este host não tem.
        from . import enriquecimento_diario

        async def _loops() -> None:
            await asyncio.gather(loop(), enriquecimento_diario.loop())

        asyncio.run(_loops())
