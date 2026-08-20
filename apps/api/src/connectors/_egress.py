"""Egresso alternativo — quando a FONTE bloqueia o IP deste servidor.

O problema é de rede, não de rota: os domínios do governo tratam o IP do host de
produção (datacenter estrangeiro) de dois jeitos, e nenhum deles é 200:

- **TransfereGov** (`api.transferegov.gestao.gov.br`, `api-publica…`) responde
  **403 com `cf-mitigated: challenge`** — desafio gerenciado da Cloudflare. Não
  adianta User-Agent de browser nem Chromium headless local com stealth: o
  desafio não é resolvido (testado, 40 s sem `cf_clearance`). O que a Cloudflare
  está reprovando é a REPUTAÇÃO DO IP, e isso um browser nosso não muda.
- **Ministério da Saúde** (`consultafns.saude.gov.br`, `sismob.saude.gov.br`)
  nem chega a responder: **TCP timeout**, bloqueio de borda por geolocalização.

Daí a regra deste módulo: só serve de fallback quem tem **egresso próprio**, ou
seja, providers REMOTOS (Crawl4AI remoto, Firecrawl). Browser local — Playwright
e Crawl4AI local — sai pelo MESMO IP reprovado e por isso fica de fora: tentar
custaria dezenas de segundos por chamada para falhar igual.

Não é scraping de página: a resposta continua sendo o JSON da API oficial, só
que buscado por outra rota de saída. O provider devolve o corpo embrulhado
(markdown com cerca ```json, ou `<pre>` do viewer do browser) e aqui ele é
desembrulhado de volta para `list`/`dict`.

Memória por HOST (`_bloqueados`): depois do primeiro 403/timeout o host inteiro
passa a ir direto pelo egresso por `TTL_BLOQUEIO`. Sem isso toda chamada pagaria
o round-trip perdido — e são centenas por coleta.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..scraping.crawl4ai import get_crawl4ai
from ..scraping.firecrawl import get_firecrawl

log = logging.getLogger(__name__)

#: quanto tempo um host fica marcado como "só pelo egresso" (segundos)
TTL_BLOQUEIO = 30 * 60

#: tentativas por provider. Provider remoto tem limite de taxa e uma coleta de
#: município dispara dezenas de chamadas seguidas: sem esta segunda tentativa um
#: 429 isolado apagava a seção inteira da proposta no painel.
TENTATIVAS = 2
ESPERA = 2.0

#: assinaturas de desafio da Cloudflare no CORPO (o header nem sempre volta)
_MARCAS_DESAFIO = (
    "just a moment",
    "um momento",
    "cf_chl_opt",
    "cf-mitigated",
    "challenges.cloudflare.com",
)

_bloqueados: dict[str, float] = {}


class EgressoIndisponivel(RuntimeError):
    """Nenhum provider com egresso próprio configurado (painel admin)."""


def host_de(url: str) -> str:
    return urlsplit(url).netloc.lower()


def marcar_bloqueado(url: str) -> None:
    _bloqueados[host_de(url)] = time.monotonic() + TTL_BLOQUEIO


def desmarcar(url: str) -> None:
    _bloqueados.pop(host_de(url), None)


def bloqueado(url: str) -> bool:
    venc = _bloqueados.get(host_de(url))
    if venc is None:
        return False
    if time.monotonic() >= venc:
        _bloqueados.pop(host_de(url), None)
        return False
    return True


def e_desafio(resp: httpx.Response) -> bool:
    """A resposta é desafio de bot (Cloudflare), não erro de rota?

    403 do PostgREST por filtro inválido também existe — por isso o teste não é
    só o status: exige a assinatura do desafio no header ou no corpo. Confundir
    os dois mandaria erro de query para o egresso e esconderia o bug real.
    """
    if resp.status_code not in (403, 503):
        return False
    if resp.headers.get("cf-mitigated"):
        return True
    corpo = resp.text[:4000].lower()
    return any(m in corpo for m in _MARCAS_DESAFIO)


def _do_markdown(md: str) -> Any:
    """Desembrulha o JSON que o provider devolveu como markdown.

    O Firecrawl entrega o corpo de uma URL JSON dentro de cerca ```json; o
    Crawl4AI às vezes entrega cru. Tenta a cerca, depois o texto inteiro, e por
    último o primeiro bloco que comece com `[` ou `{`.
    """
    if not md:
        raise ValueError("resposta vazia do egresso")
    cerca = re.search(r"```(?:json)?\s*\n(.+?)\n?```", md, re.S)
    candidatos = [cerca.group(1)] if cerca else []
    candidatos.append(md.strip())
    bloco = re.search(r"[\[{].*[\]}]", md, re.S)
    if bloco:
        candidatos.append(bloco.group(0))
    for c in candidatos:
        try:
            return json.loads(c)
        except (ValueError, TypeError):
            continue
    raise ValueError(f"corpo do egresso não é JSON: {md[:180]!r}")


def _do_html(html: str) -> Any:
    """JSON servido a um browser vem dentro de <pre> (viewer nativo)."""
    pre = re.search(r"<pre[^>]*>(.*?)</pre>", html or "", re.S)
    if not pre:
        raise ValueError("html do egresso sem <pre> com JSON")
    texto = re.sub(r"<[^>]+>", "", pre.group(1))
    return json.loads(texto.strip())


async def _providers() -> list[tuple[str, Any]]:
    """Providers com egresso PRÓPRIO, na ordem de preferência.

    Crawl4AI remoto antes do Firecrawl porque é auto-hospedado (sem custo por
    requisição); Firecrawl é o que está configurado hoje em produção.
    """
    saida = []
    for nome, prov in (("crawl4ai", get_crawl4ai()), ("firecrawl", get_firecrawl())):
        try:
            if await prov.is_enabled():
                saida.append((nome, prov))
        except Exception:  # provider mal configurado não derruba a lista
            continue
    return saida


async def get_json(url: str) -> Any:
    """Busca `url` por um egresso alternativo e devolve o JSON já decodificado."""
    providers = await _providers()
    if not providers:
        raise EgressoIndisponivel(
            "a fonte bloqueia o IP deste servidor e não há egresso alternativo "
            "configurado — defina crawl4ai_base_url ou firecrawl_api_key no "
            "painel admin (Providers & Config)"
        )
    erros: list[str] = []
    for nome, prov in providers:
        r = None
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                r = await prov.scrape(url, formats=["markdown", "rawHtml"])
                break
            except Exception as exc:
                erros.append(f"{nome} (tentativa {tentativa}): {type(exc).__name__}: {exc}")
                if tentativa < TENTATIVAS:
                    await asyncio.sleep(ESPERA)
        if r is None:
            continue
        for desembrulha, chave in ((_do_markdown, "markdown"), (_do_html, "rawHtml")):
            try:
                dados = desembrulha(r.get(chave) or "")
            except Exception as exc:
                erros.append(f"{nome}/{chave}: {exc}")
                continue
            log.info("egresso: %s respondeu por %s (%s)", host_de(url), nome, chave)
            return dados
    raise EgressoIndisponivel(f"egresso alternativo falhou em {url} — {'; '.join(erros[:4])}")
