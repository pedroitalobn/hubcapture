"""Auditoria das propostas vindas de scraping — remove o que não é proposta.

Terceira e última etapa do gate de ingestão, e a única que roda DEPOIS da
gravação: a triagem determinística (`ingestion/validador.py`) barra o resíduo
óbvio na porta do upsert, e o que passou parecendo dado é revisto aqui pela IA
configurada no painel (`ai/validacao.py`).

Fora do request, sempre — é o mesmo desenho de `jobs/curadoria.curar_com_ia`:
lote pequeno, concorrência limitada, chamado pelo 1º sync e pelo refresh
diário. Nunca dentro de uma requisição do painel.

RECORTE: só audita registro que veio de SCRAPING. Linha de API é estruturada —
o que ela devolve como valor de campo é o valor daquele campo, sem parser de
tabela no meio. Rodar a IA sobre elas seria custo sem hipótese de erro, e
abriria a porta para a IA apagar dado de API por engano.

CURSOR: `propostas.validacao_ia` marca quem já foi auditada. NULL = pendente.
Veredito indefinido (IA desligada, rede fora) NÃO grava nada — a proposta fica
pendente e é reavaliada quando houver credencial, em vez de ficar aprovada por
omissão.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Text, cast, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.validacao import Veredito, analisar
from ..models.proposta import Proposta
from ..schemas.proposta import PropostaCanonica

log = logging.getLogger("hubcapture.jobs.validacao")

#: lote por rodada — chamada de LLM por registro, mesmo custo da curadoria
LOTE = 20
#: chamadas simultâneas ao LLM dentro do lote
_PARALELAS = 4


@dataclass
class Auditoria:
    """Resultado de uma rodada — o que a IA aprovou, removeu e não julgou."""

    aprovadas: int = 0
    removidas: int = 0
    indefinidas: int = 0
    motivos: list[str] = field(default_factory=list)


def _canonica(p: Proposta) -> PropostaCanonica:
    """A proposta persistida de volta ao formato que a auditoria lê."""
    return PropostaCanonica(
        fonte=p.fonte,
        id_externo=p.id_externo,
        numero_proposta=p.numero_proposta,
        titulo=p.titulo,
        objeto=p.objeto,
        orgao_superior=p.orgao_superior,
        modalidade=p.modalidade,
        municipio_ibge=p.municipio_ibge,
        municipio_nome=p.municipio_nome,
        uf=p.uf,
        valor_total=p.valor_total,
        situacao=p.situacao,
        execucao=p.execucao,
    )


def _condicao_veio_de_scraping():
    """Filtro SQL de proveniência com marca de scraping.

    `proveniencia` é {campo: 'api'|'scrape', '_fonte': …}; o texto `"scrape"`
    só aparece ali como VALOR (nenhum campo do schema canônico se chama assim).
    Comparar o jsonb serializado evita depender de jsonpath e mantém o filtro
    legível — o conjunto é pequeno (só o que ainda não foi auditado).
    """
    return cast(Proposta.proveniencia, Text).like('%"scrape"%')


async def auditar_com_ia(session: AsyncSession, limite: int = LOTE) -> Auditoria:
    """Uma rodada de auditoria. Remove só o que a IA reprovou EXPLICITAMENTE."""
    stmt = (
        select(Proposta)
        .where(Proposta.validacao_ia.is_(None), _condicao_veio_de_scraping())
        .limit(limite)
    )
    pendentes = list((await session.execute(stmt)).scalars().all())
    if not pendentes:
        return Auditoria()

    semaforo = asyncio.Semaphore(_PARALELAS)

    async def auditar(p: Proposta) -> tuple[Proposta, Veredito | None]:
        async with semaforo:
            return p, await analisar(_canonica(p))

    resultados = await asyncio.gather(*(auditar(p) for p in pendentes), return_exceptions=True)

    auditoria = Auditoria()
    agora = datetime.now(UTC)
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            # `analisar` já absorve as suas falhas; o que chega aqui é falha da
            # própria tarefa. Sem veredito, a proposta fica (e segue pendente).
            log.warning("auditoria de proposta falhou", exc_info=resultado)
            auditoria.indefinidas += 1
            continue
        p, veredito = resultado
        if veredito is None:  # "não sei" → mantém e reavalia na próxima rodada
            auditoria.indefinidas += 1
            continue
        if veredito.valido:
            await session.execute(
                update(Proposta)
                .where(Proposta.id == p.id)
                .values(
                    validacao_ia={
                        "veredito": "aprovada",
                        "motivo": veredito.motivo,
                        "em": agora.isoformat(),
                    }
                )
            )
            auditoria.aprovadas += 1
            continue
        # reprovada: resíduo de coleta que passou pela triagem determinística.
        # Registrado em log ANTES de sumir — remoção por IA nunca é silenciosa.
        log.warning(
            "auditoria por IA removeu proposta %s/%s (%s): %s",
            p.fonte,
            p.id_externo,
            p.municipio_ibge,
            veredito.motivo,
        )
        await session.execute(delete(Proposta).where(Proposta.id == p.id))
        auditoria.removidas += 1
        auditoria.motivos.append(f"{p.fonte}/{p.id_externo}: {veredito.motivo}")
    return auditoria
