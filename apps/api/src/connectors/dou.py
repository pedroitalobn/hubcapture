"""Diário Oficial da União — Seção 3, a PROVA da publicação.

O campo "Publicação" da ficha do TransfereGov é a declaração do sistema. A
publicação em si é um ato que acontece FORA dele: o extrato do contrato de
repasse sai no DOU **Seção 3**, e é isso que o gestor precisa poder apontar.

Daí a segunda via de conferência, que o cliente descreveu assim: proposta
publicada **sempre tem nota de empenho** — nunca se publica sem NE —, então
procurar no DOU Seção 3 por aquela NE naquele município responde a pergunta por
um caminho independente do campo. O extrato traz os dois na mesma linha::

    EXTRATO DE CONTRATO
    Contrato de Repasse nº 999293/2026, firmado pelo MUNICÍPIO DE APUIARÉS-CE,
    CNPJ 07.438.468/0001-01, junto à União Federal por intermédio do MINISTÉRIO
    DO ESPORTE … NE 2026NE001244 … Assinado em 18/06/2026

Este connector só CONFIRMA. Não achar nada no DOU não é "não foi publicado" —
é não ter achado: a busca é textual, o termo pode sair grafado de outro jeito e
a fonte pode estar fora do ar. Quem nega é o campo da ficha, e só quando ele
nega explicitamente (§56b). Confundir as duas coisas devolveria o falso
positivo pelo avesso: um falso NEGATIVO, o gestor achando que perdeu o prazo de
uma publicação que saiu.

Rota (ponto de calibração, §27): a busca pública do in.gov.br devolve HTML com
os resultados embutidos num `<script id="params">` em JSON — é assim desde a
reforma do portal. `dou_busca_url` e `dou_secao` ficam no painel admin.
"""

from __future__ import annotations

import html as html_
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from ..services import config as config_service
from . import _egress
from ._http import TIMEOUT

log = logging.getLogger(__name__)

SOURCE_ID = "dou"

#: Seção 3 é onde saem contratos, convênios e seus extratos.
SECAO_CONTRATOS = "do3"

#: teto de resultados por termo — a busca pagina, e o que interessa é achar UM
#: extrato que case; varrer o histórico inteiro seria custo sem resposta nova.
MAX_RESULTADOS = 20

#: A NE como o SIAFI a escreve, e como ela aparece no extrato: 2026NE001244.
RE_NOTA_EMPENHO = re.compile(r"\b(\d{4}NE\d{6})\b", re.I)

_SCRIPT_PARAMS = re.compile(
    r"<script[^>]+id=[\"']params[\"'][^>]*>(.*?)</script>", re.S | re.I
)
_TAGS = re.compile(r"<[^>]+>")
_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

_CABECALHOS = {
    # a busca do in.gov.br responde HTML de portal; sem User-Agent de browser
    # ela devolve página de erro em vez de resultado
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


class DouIndisponivel(RuntimeError):
    """A busca do DOU não respondeu — diferente de "não achei nada"."""


@dataclass(frozen=True)
class Publicacao:
    """Uma matéria do DOU que casou a busca."""

    titulo: str
    texto: str
    data: date | None = None
    edicao: str | None = None
    secao: str | None = None
    url: str | None = None
    bruto: dict = field(default_factory=dict)


def normalizar(texto: Any) -> str:
    """Minúsculas, sem acento e com espaço colapsado — o extrato do DOU chega
    com hifenização e quebra de coluna no meio das palavras."""
    plano = unicodedata.normalize("NFD", str(texto or ""))
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", plano).strip()


def so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _texto(bruto: str) -> str:
    return " ".join(html_.unescape(_TAGS.sub(" ", bruto or "")).split())


def _data(valor: Any) -> date | None:
    m = _DATA_BR.search(str(valor or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _primeiro(item: dict, *chaves: str) -> Any:
    for c in chaves:
        if item.get(c) not in (None, ""):
            return item[c]
    return None


def _url(item: dict) -> str | None:
    alvo = _primeiro(item, "urlTitle", "url", "link")
    if not alvo:
        return None
    alvo = str(alvo)
    if alvo.startswith("http"):
        return alvo
    return f"https://www.in.gov.br/web/dou/-/{alvo.lstrip('/')}"


def parse_resultados(pagina: str) -> list[Publicacao]:
    """Os resultados embutidos no HTML da busca.

    O portal serve a lista num `<script id="params">`; ler o JSON é
    determinístico, ao contrário de raspar os cards renderizados. Página sem o
    script é página de erro/desafio — e isso é INDISPONÍVEL, não vazio: devolver
    lista vazia aqui faria "não consegui perguntar" virar "não foi publicado".
    """
    m = _SCRIPT_PARAMS.search(pagina or "")
    if not m:
        raise DouIndisponivel(
            "a busca do DOU não devolveu a lista de resultados "
            "(página de erro/desafio, ou o portal mudou o formato)"
        )
    try:
        dados = json.loads(html_.unescape(m.group(1).strip()))
    except json.JSONDecodeError as exc:
        raise DouIndisponivel(f"resultados do DOU ilegíveis: {exc}") from exc
    itens = dados.get("jsonArray") if isinstance(dados, dict) else None
    saida: list[Publicacao] = []
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        saida.append(
            Publicacao(
                titulo=_texto(str(_primeiro(item, "title", "artType") or "")),
                texto=_texto(str(_primeiro(item, "content", "abstract", "text") or "")),
                data=_data(_primeiro(item, "pubDate", "editionDate", "date")),
                edicao=str(_primeiro(item, "editionNumber", "edition") or "") or None,
                secao=str(_primeiro(item, "pubName", "section") or "") or None,
                url=_url(item),
                bruto=item,
            )
        )
        if len(saida) >= MAX_RESULTADOS:
            break
    return saida


async def _base_url() -> str:
    from ..core.config import settings

    return (await config_service.resolver("dou_busca_url")) or settings.dou_busca_url


async def _secao() -> str:
    from ..core.config import settings

    return (
        await config_service.resolver("dou_secao")
    ) or settings.dou_secao or SECAO_CONTRATOS


async def _baixar(url: str, params: dict[str, str]) -> str:
    """O HTML da busca — direto, e pelo egresso quando o IP é recusado.

    Mesmo desenho de `_http.get_json`: gov.br responde 403 com desafio da
    Cloudflare para o IP deste servidor, e isso não se resolve com retry. A
    diferença é que aqui a resposta é HTML, então quem serve de egresso é o
    scraper remoto (que devolve a página inteira), não o desembrulhador de JSON.
    """
    completa = str(httpx.URL(url).copy_merge_params(params))
    if not _egress.bloqueado(completa):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=_CABECALHOS)
            if not _egress.e_desafio(resp):
                resp.raise_for_status()
                _egress.desmarcar(completa)
                return resp.text
            _egress.marcar_bloqueado(completa)
            log.warning("DOU: busca desafiada pela Cloudflare — tentando scraper remoto")
        except httpx.TransportError as exc:
            _egress.marcar_bloqueado(completa)
            log.warning("DOU: busca inacessível daqui (%s) — tentando scraper remoto", exc)
        except httpx.HTTPStatusError as exc:
            raise DouIndisponivel(f"busca do DOU respondeu {exc.response.status_code}") from exc

    from ..scraping.scraper import ScraperNotConfigured, get_scraper

    try:
        resultado = await get_scraper().scrape(completa, ["html", "rawHtml"])
    except ScraperNotConfigured as exc:
        raise DouIndisponivel(
            "o DOU recusa o IP deste servidor e nenhum scraper com egresso "
            "próprio está configurado (painel admin → Scraping)"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — provider fora do ar não é "não publicado"
        raise DouIndisponivel(f"não foi possível consultar o DOU: {exc}") from exc
    pagina = resultado.get("rawHtml") or resultado.get("html") or ""
    if not pagina:
        raise DouIndisponivel("o scraper devolveu a página do DOU vazia")
    return pagina


async def buscar(termo: str, *, secao: str | None = None) -> list[Publicacao]:
    """Matérias da seção que casam o termo (busca textual do portal)."""
    termo = str(termo or "").strip()
    if not termo:
        return []
    base = await _base_url()
    params = {
        "q": f'"{termo}"',  # aspas: o portal casa a expressão, não as palavras soltas
        "s": secao or await _secao(),
        "exactDate": "all",
        "sortType": "0",
        "delta": str(MAX_RESULTADOS),
    }
    return parse_resultados(await _baixar(base, params))


async def health_check() -> bool:
    try:
        await buscar("extrato de contrato de repasse")
        return True
    except Exception:  # noqa: BLE001 — health nunca levanta
        return False
