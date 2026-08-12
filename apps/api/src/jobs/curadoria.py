"""Curadoria das propostas — pílulas de categoria e resumo por IA.

Dois passes, deliberadamente separados pelo custo:

- `classificar_pendentes`: determinístico (palavra-chave), sem rede. Roda no fim
  de TODA coleta — inclusive na busca ao vivo do painel — porque é barato o
  bastante para caber dentro do request. Garante pílula em toda proposta.
- `curar_com_ia`: chama o LLM (resumo + categorias refinadas). NUNCA roda dentro
  de um request: entra no 1º sync e no cron, em lote pequeno. Sem credencial de
  LLM, o `gerar_curadoria` já devolve o determinístico e o pass vira quase no-op.

Segue o padrão de `jobs/embed.py`: recebe a sessão de quem chama (o RLS vale) e
devolve quantas linhas tocou.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai import categorias as categorias_ai
from ..ai.resumo import gerar_curadoria
from ..models.proposta import Proposta
from ..schemas.proposta import PropostaCanonica

log = logging.getLogger("hubcapture.jobs.curadoria")

# lote da passada com IA: pequeno de propósito (custo por chamada e latência).
LOTE_IA = 20
# concorrência das chamadas ao LLM dentro do lote
_PARALELAS = 4


def _canonica(p: Proposta) -> PropostaCanonica:
    return PropostaCanonica(
        fonte=p.fonte,
        id_externo=p.id_externo,
        titulo=p.titulo,
        objeto=p.objeto,
        orgao_superior=p.orgao_superior,
        modalidade=p.modalidade,
        municipio_ibge=p.municipio_ibge,
        valor_total=p.valor_total,
        situacao=p.situacao,
    )


def categorias_de(p: Proposta) -> list[str]:
    """Classificação determinística de uma proposta já persistida."""
    return categorias_ai.classificar(p.titulo, p.objeto, p.orgao_superior, p.modalidade)


async def classificar_pendentes(session: AsyncSession, limite: int = 500) -> int:
    """Preenche `categorias_ia` de quem ainda não tem. Sem rede — cabe no request."""
    stmt = (
        select(Proposta)
        .where(Proposta.categorias_ia.is_(None), Proposta.excluido_em.is_(None))
        .limit(limite)
    )
    pendentes = list((await session.execute(stmt)).scalars().all())
    tocadas = 0
    for p in pendentes:
        slugs = categorias_de(p)
        # grava mesmo a lista vazia: marca "já classificado" e evita reprocessar
        await session.execute(
            update(Proposta).where(Proposta.id == p.id).values(categorias_ia=slugs)
        )
        tocadas += 1
    return tocadas


async def curar_com_ia(
    session: AsyncSession, limite: int = LOTE_IA, papel: str = "executivo"
) -> int:
    """Gera `resumo_ia` (+ categorias refinadas) para as propostas sem resumo.

    Best-effort: uma proposta que falhar não derruba o lote — `gerar_curadoria`
    já absorve a falha e devolve o determinístico.
    """
    stmt = (
        select(Proposta)
        .where(Proposta.resumo_ia.is_(None), Proposta.excluido_em.is_(None))
        .limit(limite)
    )
    pendentes = list((await session.execute(stmt)).scalars().all())
    if not pendentes:
        return 0

    semaforo = asyncio.Semaphore(_PARALELAS)

    async def curar(p: Proposta):
        async with semaforo:
            return p, await gerar_curadoria(_canonica(p), papel)

    resultados = await asyncio.gather(*(curar(p) for p in pendentes), return_exceptions=True)

    tocadas = 0
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            log.warning("curadoria de proposta falhou", exc_info=resultado)
            continue
        p, curadoria = resultado
        valores: dict = {"categorias_ia": curadoria.categorias}
        if curadoria.resumo:
            valores["resumo_ia"] = curadoria.resumo
        await session.execute(update(Proposta).where(Proposta.id == p.id).values(**valores))
        tocadas += 1
    return tocadas
