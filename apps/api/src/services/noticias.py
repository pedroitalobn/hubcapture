"""Painel informativo — notícias do TransfereGov (gov.br).

O fluxograma pede um painel puxando as notícias oficiais. gov.br (Plone) expõe
RSS em `<listagem>/RSS`; a URL é calibrável no painel admin
(`transferegov_noticias_url`). Parse leve com stdlib (ElementTree), cache em
memória (TTL 1h) e degradação para lista vazia — notícia nunca derruba request.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from . import config as config_service

DEFAULT_URL = "https://www.gov.br/transferegov/pt-br/noticias/noticias/RSS"
TTL_SEGUNDOS = 3600
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

_cache: tuple[float, list[Noticia]] | None = None


@dataclass
class Noticia:
    titulo: str
    url: str
    data: str | None
    resumo: str | None


def _texto(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def parse_rss(xml_texto: str) -> list[Noticia]:
    """Extrai os itens de um feed RSS (tolerante a namespaces do Plone)."""
    root = ET.fromstring(xml_texto)
    noticias = []
    for item in root.iter("item"):
        titulo = _texto(item, "title")
        link = _texto(item, "link")
        if not titulo or not link:
            continue
        noticias.append(
            Noticia(
                titulo=titulo,
                url=link,
                data=_texto(item, "pubDate")
                or _texto(item, "{http://purl.org/dc/elements/1.1/}date"),
                resumo=_texto(item, "description"),
            )
        )
    return noticias


async def listar(limite: int = 10) -> list[Noticia]:
    """Notícias do TransfereGov, cache 1h. Falha de rede/parse → lista vazia."""
    global _cache
    agora = time.monotonic()
    if _cache and agora - _cache[0] < TTL_SEGUNDOS:
        return _cache[1][:limite]
    url = await config_service.resolver("transferegov_noticias_url") or DEFAULT_URL
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        noticias = parse_rss(resp.text)
    except Exception:
        return _cache[1][:limite] if _cache else []
    _cache = (agora, noticias)
    return noticias[:limite]
