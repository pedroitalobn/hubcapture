"""Enriquecimento diário — pareceres e empenhos JÁ NO BANCO, vinculados.

O caminho on-demand (abrir a proposta no painel) coleta na hora, mas obriga o
primeiro visitante a esperar browser/fonte. Este job vira o jogo: varre as
propostas do território de madrugada e deixa parecer e empenho gravados e
vinculados (pelas mesmas chaves que as telas usam — nº da proposta e código do
plano de ação), de modo que o painel só LÊ.

INCREMENTAL POR DESENHO — coletado uma vez, não coleta de novo à toa:

  1. quem NUNCA foi enriquecido entra primeiro (ano mais novo antes — é o que
     o gestor está acompanhando);
  2. quem já foi enriquecido e segue VIVO (situação não terminal e safra
     recente) volta à fila só depois de `REVISITA_DIAS`;
  3. proposta TERMINAL (rejeitada/eliminada/cancelada) já enriquecida não
     volta nunca — o parecer de uma proposta rejeitada em 2018 não muda mais.

O carimbo fica em `propostas.execucao['enriquecimento']` (quando rodou e se a
proposta ainda estava viva), então o estado sobrevive a deploy e é visível por
SQL. Os TETOS por rodada existem porque cada universo cobra num recurso
diferente: o webapp do SIconv custa TEMPO de browser; os módulos de API custam
requisições do egresso (Firecrawl é pago). Com fila ordenada + teto, a primeira
varredura converge em dias e depois o job fica barato.

Roda no MESMO processo do `worker` (refresh_diario agenda os dois loops): mais
um container só para isto custaria memória que este host não tem.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from ..db.session import SessionLocal, engine
from ..models.proposta import Proposta

log = logging.getLogger(__name__)

HORA_UTC = int(os.getenv("ENRIQUECIMENTO_HORA_UTC", "8"))
ATIVO = os.getenv("ENRIQUECIMENTO_ATIVO", "1") not in ("0", "false", "False")
#: quantas propostas por rodada passam pelo webapp do SIconv (browser local)
TETO_WEBAPP = int(os.getenv("ENRIQUECIMENTO_TETO_WEBAPP", "120"))
#: quantas propostas por rodada consultam módulos de API (egresso pago)
TETO_API = int(os.getenv("ENRIQUECIMENTO_TETO_API", "300"))
#: proposta viva volta à fila depois deste prazo
REVISITA_DIAS = int(os.getenv("ENRIQUECIMENTO_REVISITA_DIAS", "3"))
#: tamanho do lote por sessão de browser (sessão guest expira; lote curto
#: também limita o estrago de uma queda no meio)
LOTE_WEBAPP = 25

LOCK_ID = 8_140_233_903

#: situação que encerra a vida da proposta — enriquecida uma vez, nunca mais
_TERMINAIS = ("rejeitad", "eliminad", "cancelad", "anulad", "excluid")

_SQL_FILA = """
SELECT id, fonte, id_externo, numero_proposta, municipio_ibge,
       (execucao -> 'enriquecimento' ->> 'em') AS enriquecido_em,
       coalesce(situacao, '') AS situacao,
       coalesce((execucao ->> 'ano')::int, 0) AS ano
FROM propostas
WHERE fonte = ANY(:fontes)
  AND id_externo ~ '^[0-9]+$'
  AND (
        (execucao -> 'enriquecimento' ->> 'em') IS NULL
        OR (
             (execucao -> 'enriquecimento' ->> 'em')::timestamptz < :limite
             AND NOT (lower(coalesce(situacao, '')) SIMILAR TO :terminais)
             AND coalesce((execucao ->> 'ano')::int, 0) >= :ano_minimo
           )
      )
ORDER BY (execucao -> 'enriquecimento' ->> 'em') IS NOT NULL,  -- nunca-enriquecida primeiro
         coalesce((execucao ->> 'ano')::int, 0) DESC
LIMIT :teto
"""


def _padrao_terminais() -> str:
    return "%(" + "|".join(_TERMINAIS) + ")%"


async def _fila(session, fontes: list[str], teto: int) -> list[dict]:
    limite = datetime.now(UTC) - timedelta(days=REVISITA_DIAS)
    ano_minimo = datetime.now(UTC).year - 2
    linhas = await session.execute(
        text(_SQL_FILA),
        {
            "fontes": fontes,
            "limite": limite,
            "terminais": _padrao_terminais(),
            "ano_minimo": ano_minimo,
            "teto": teto,
        },
    )
    return [dict(x) for x in linhas.mappings().all()]


async def _flag_plataforma(session) -> None:
    """Liga a bandeira de plataforma NA TRANSAÇÃO CORRENTE.

    `set_config(..., true)` é transaction-local e o job COMMITA por proposta —
    a bandeira morre no primeiro commit e, sem ela, o `ON CONFLICT DO UPDATE`
    (que aplica a policy de SELECT sobre a linha existente, §50) recusa a linha
    seguinte com "new row violates row-level security policy". Por isso ela é
    religada no início de cada transação, nunca no início da sessão. A variante
    session-level (is_local=false) contaminaria a conexão devolvida ao pool —
    este worker também roda o refresh por-tenant no MESMO processo.
    """
    await session.execute(text("SELECT set_config('app.plataforma', 'on', true)"))


async def _carimbar(session, proposta_id, situacao: str) -> None:
    """Grava o carimbo de enriquecimento no JSONB da proposta."""
    viva = not any(t in situacao.lower() for t in _TERMINAIS)
    await session.execute(
        text(
            "UPDATE propostas SET execucao = coalesce(execucao, '{}'::jsonb) || "
            "jsonb_build_object('enriquecimento', jsonb_build_object("
            "'em', CAST(:em AS text), 'viva', CAST(:viva AS boolean))) "
            "WHERE id = :id"
        ),
        {"em": datetime.now(UTC).isoformat(), "viva": viva, "id": proposta_id},
    )


def _decimal_br(v: str | None) -> str | None:
    """"8.048.614,32" → "8048614.32" (texto pronto p/ jsonb; None passa)."""
    if not v:
        return None
    return v.replace(".", "").replace(",", ".")


async def _carimbar_execucao_webapp(session, proposta_id, item: dict) -> None:
    """O que o webapp respondeu sobre EXECUÇÃO vai para `propostas.execucao`.

    São os três dados do header do detalhe — publicou? empenhou? pagou? — na
    versão VIVA (a listagem de repasses muda no dia do desembolso; o pacote
    público, ~mensal). `valor_pago` aqui SOBRESCREVE o do pacote de propósito:
    é o mesmo dado, mais novo.
    """
    ex = item.get("execucao") or {}
    rep = item.get("repasses") or {}
    payload = {
        "valor_pago": _decimal_br(rep.get("valor_desembolsado")),
        "situacao_publicacao": ex.get("situacao_publicacao"),
        "webapp": {
            # a MESMA situação também fica carimbada aqui: é o que permite a
            # tela dizer que o "Publicado" exibido veio da consulta ao vivo, e
            # não do pacote (~mensal). Sem a marca, divergência com o portal
            # vira discussão sem evidência (§56).
            "situacao_publicacao": ex.get("situacao_publicacao"),
            "situacao_instrumento": ex.get("situacao_instrumento"),
            "empenhado": ex.get("empenhado_flag"),
            "situacao_siafi": ex.get("situacao_siafi"),
            "instrumento": ex.get("instrumento"),
            "processo": ex.get("processo"),
            "valor_repasse_total": _decimal_br(rep.get("valor_repasse_total")),
            "valor_a_desembolsar": _decimal_br(rep.get("valor_a_desembolsar")),
            "data_ultimo_desembolso": rep.get("data_ultimo_desembolso"),
        },
    }
    payload["webapp"] = {k: v for k, v in payload["webapp"].items() if v}
    payload = {k: v for k, v in payload.items() if v}
    if not payload:
        return
    import json

    await session.execute(
        text(
            "UPDATE propostas SET execucao = coalesce(execucao, '{}'::jsonb) || "
            "CAST(:novo AS jsonb) WHERE id = :id"
        ),
        {"novo": json.dumps(payload, ensure_ascii=False), "id": proposta_id},
    )


async def _enriquecer_siconv(session, fila: list[dict]) -> dict[str, int]:
    """Universo discricionárias/legais: webapp em lote (uma sessão de browser)."""
    from ..connectors import pareceres_siconv
    from ..ingestion.normalizer_empenho import normalize_empenho
    from ..ingestion.normalizer_parecer import normalize_parecer
    from ..services.empenhos_proposta import _upsert as upsert_empenhos
    from ..services.pareceres import _upsert as upsert_pareceres

    totais = {"propostas": 0, "pareceres": 0, "empenhos": 0, "erros": 0}
    conn = pareceres_siconv.get_connector()
    por_id = {str(p["id_externo"]): p for p in fila}
    ids = list(por_id)
    for inicio in range(0, len(ids), LOTE_WEBAPP):
        lote = ids[inicio : inicio + LOTE_WEBAPP]
        coletado = await conn.coletar_lote(lote)
        for id_ext, item in coletado.items():
            p = por_id[id_ext]
            await _flag_plataforma(session)
            if item.get("erro"):
                totais["erros"] += 1
                continue
            chave = str(p["numero_proposta"] or id_ext)
            pareceres = [
                normalize_parecer(
                    b,
                    numero_plano_trabalho=chave,
                    fonte=pareceres_siconv.SOURCE_ID,
                    numero_proposta=p["numero_proposta"],
                    municipio_ibge=p["municipio_ibge"],
                )
                for b in item["pareceres"]
            ]
            if pareceres:
                await upsert_pareceres(session, pareceres)
            # só entra a nota que o cache (pacote diário) ainda não tem —
            # senão o mesmo empenho apareceria por duas fontes
            ja_tem = {
                x
                for (x,) in (
                    await session.execute(
                        text(
                            "SELECT numero_empenho FROM proposta_empenhos "
                            "WHERE numero_proposta = :np AND numero_empenho IS NOT NULL"
                        ),
                        {"np": p["numero_proposta"]},
                    )
                ).all()
            }
            empenhos = [
                normalize_empenho(
                    b,
                    fonte=pareceres_siconv.SOURCE_ID_EMPENHO,
                    numero_proposta=p["numero_proposta"],
                    numero_plano_acao=None,
                    municipio_ibge=p["municipio_ibge"],
                )
                for b in item["empenhos"]
                if b.get("numero_empenho") not in ja_tem
            ]
            if empenhos:
                await upsert_empenhos(session, empenhos)
            await _carimbar_execucao_webapp(session, p["id"], item)
            await _carimbar(session, p["id"], p["situacao"])
            await session.commit()
            totais["propostas"] += 1
            totais["pareceres"] += len(pareceres)
            totais["empenhos"] += len(empenhos)
    return totais


async def _enriquecer_api(session, fila: list[dict]) -> dict[str, int]:
    """Universos com API (fundo a fundo e especiais): services por proposta."""
    from ..services import empenhos_proposta as emp_svc
    from ..services import pareceres as par_svc

    totais = {"propostas": 0, "pareceres": 0, "empenhos": 0, "erros": 0}
    for p in fila:
        try:
            await _flag_plataforma(session)
            proposta = await session.get(Proposta, p["id"])
            if proposta is None:
                continue
            itens, coleta = await par_svc.por_proposta(
                session, proposta.id, atualizar=True, usuario_id=None
            )
            _, _, coleta_emp = await emp_svc.por_proposta(
                session, proposta, atualizar=True, usuario_id=None
            )
            if "erro" in (coleta.status, coleta_emp.status):
                totais["erros"] += 1
            else:
                await _carimbar(session, p["id"], p["situacao"])
                totais["propostas"] += 1
                totais["pareceres"] += coleta.total or 0
                totais["empenhos"] += coleta_emp.total or 0
            await session.commit()
        except Exception:  # noqa: BLE001 — uma proposta não derruba o sweep
            totais["erros"] += 1
            log.warning("enriquecimento api: proposta %s falhou", p["id"], exc_info=True)
    return totais


async def sweep() -> dict:
    """Uma rodada: monta as filas, enriquece dentro dos tetos, carimba."""
    async with engine.connect() as lock_conn:
        travou = (
            await lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})
        ).scalar()
        if not travou:
            log.warning("enriquecimento: outra rodada em andamento — pulando")
            return {"status": "ocupado"}
        try:
            async with SessionLocal() as session:
                # o job é da plataforma: enxerga o cache inteiro, não um tenant
                await _flag_plataforma(session)
                fila_web = await _fila(
                    session, ["transferegov_disc", "transferegov_voluntarias"], TETO_WEBAPP
                )
                fila_api = await _fila(
                    session, ["transferegov_ff", "transferegov_esp"], TETO_API
                )
                log.info(
                    "enriquecimento: fila webapp=%d, fila api=%d",
                    len(fila_web),
                    len(fila_api),
                )
                r_web = await _enriquecer_siconv(session, fila_web)
                r_api = await _enriquecer_api(session, fila_api)
            resumo = {"status": "ok", "webapp": r_web, "api": r_api}
            log.info("enriquecimento: %s", resumo)
            return resumo
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})


def _segundos_ate_proxima_execucao(agora: datetime) -> float:
    alvo = agora.replace(hour=HORA_UTC, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def loop() -> None:
    if not ATIVO:
        log.warning("enriquecimento: desativado por ENRIQUECIMENTO_ATIVO")
        return
    log.info("enriquecimento diário: agendado para %02d:00 UTC", HORA_UTC)
    while True:
        espera = _segundos_ate_proxima_execucao(datetime.now(UTC))
        log.info("enriquecimento: próxima rodada em %.0f min", espera / 60)
        await asyncio.sleep(espera)
        try:
            await sweep()
        except Exception:  # noqa: BLE001 — a rodada de amanhã tenta de novo
            log.exception("enriquecimento: rodada falhou")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if os.getenv("RODAR_AGORA") == "1":
        asyncio.run(sweep())
    else:
        asyncio.run(loop())
