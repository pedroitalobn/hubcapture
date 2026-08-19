"""Coleta combinada — API e scraping como DUAS fontes de verdade.

Antes, o scraping era plano B: só rodava quando a API falhava, e o que a página
mostrava a mais (situação atualizada, execução financeira do painel) simplesmente
se perdia sempre que a API respondia. Aqui os dois lados rodam **juntos** e o
resultado é aglutinado: cada campo fica com o lado que tem mais autoridade sobre
ele (`ingestion/merge.py`), e `proveniencia` registra de onde veio cada valor.

As quatro combinações possíveis, todas úteis:
  API ok  + scrape ok    → registro aglutinado (o caso que interessa)
  API ok  + scrape falha → API pura (nada pior que antes)
  API falha + scrape ok  → scraping vira a fonte primária (o antigo fallback)
  ambos falham           → levanta o erro da API (o serviço registra em sync_runs)

O casamento entre os dois lados é pelo NÚMERO da transferência/convênio, que é o
identificador que aparece tanto na API quanto no painel — comparado só por
dígitos, porque a página escreve "123456/2024" onde a API devolve 1234562024.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("hubcapture.connectors.combinada")

#: chave onde o payload de scraping viaja dentro do `raw` do RawRecord
CHAVE_SCRAPE = "_scrape"

#: campos que costumam carregar o número da transferência/convênio
CHAVES_NUMERO = (
    "numero",
    "numero_proposta",
    "numero_convenio",
    "nr_convenio",
    "id_externo",
    "id_plano_acao",
    "transferencia",
)


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def chave_de(linha: dict[str, Any]) -> str:
    """Número da linha (API ou scraping), só dígitos — '' se não achar."""
    for chave in CHAVES_NUMERO:
        if chave in linha and _digitos(linha[chave]):
            return _digitos(linha[chave])
    # o scraping às vezes traz o número numa coluna com rótulo livre
    for chave, valor in linha.items():
        if "numero" in str(chave).lower() or "transferencia" in str(chave).lower():
            if _digitos(valor):
                return _digitos(valor)
    return ""


async def coletar(
    api: Callable[[], Awaitable[list[dict]]],
    scrape: Callable[[], Awaitable[list[dict]]],
    *,
    fonte: str,
) -> tuple[list[dict], list[dict], Exception | None]:
    """Roda os dois lados em paralelo. Devolve (linhas_api, linhas_scrape, erro_api).

    Nenhum lado derruba o outro: a exceção de cada um é capturada e logada. O
    erro da API volta para o chamador decidir (se o scraping também vier vazio,
    ele é relevado para o serviço registrar o incidente em `sync_runs`).
    """
    resultados = await asyncio.gather(api(), scrape(), return_exceptions=True)
    linhas_api, linhas_scrape = resultados
    erro_api: Exception | None = None

    if isinstance(linhas_api, BaseException):
        erro_api = linhas_api if isinstance(linhas_api, Exception) else None
        log.info("coleta combinada %s: API falhou (%s)", fonte, linhas_api)
        linhas_api = []
    if isinstance(linhas_scrape, BaseException):
        log.info("coleta combinada %s: scraping falhou (%s)", fonte, linhas_scrape)
        linhas_scrape = []

    return list(linhas_api or []), list(linhas_scrape or []), erro_api


def aglutinar(
    linhas_api: list[dict],
    linhas_scrape: list[dict],
) -> list[tuple[dict, dict | None]]:
    """Pareia cada linha da API com a linha de scraping do mesmo número.

    Linha de scraping sem par na API entra sozinha (a página conhece transferência
    que a API ainda não publicou) — é o ganho de tratar o scraping como fonte, e
    não como plano B.

    NENHUMA linha some aqui. A versão anterior indexava o scraping por número e
    devolvia só o índice: linha sem número identificável era descartada quando
    ALGUMA outra tinha número (a página mistura os dois casos o tempo todo), e
    duas linhas com o mesmo número colapsavam numa só. O município que trazia 5
    transferências da página chegava ao painel com 1 — e o gestor lia isso como
    "a fonte só tem uma", que é o pior erro possível para quem usa o Hub para
    decidir. Agora o índice serve APENAS para casar com a API; toda linha de
    scraping não casada sai na lista, com número ou sem.
    """
    # número → linhas de scraping (lista: número repetido não colapsa)
    indice: dict[str, list[dict]] = {}
    for linha in linhas_scrape:
        chave = chave_de(linha)
        if chave:
            indice.setdefault(chave, []).append(linha)

    pares: list[tuple[dict, dict | None]] = []
    pareadas: list[int] = []  # id() das linhas de scraping já usadas
    for linha in linhas_api:
        chave = chave_de(linha)
        candidatas = indice.get(chave) if chave else None
        par = None
        if candidatas:
            # cada linha da página casa com UMA da API: consome a primeira livre
            par = candidatas.pop(0)
            pareadas.append(id(par))
        pares.append((linha, par))

    # tudo que a página trouxe e não casou com a API entra como registro próprio
    pares.extend(({}, linha) for linha in linhas_scrape if id(linha) not in pareadas)

    return pares
