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

#: O PDF CERTIFICADO da página do jornal — é o documento que o gestor anexa ao
#: processo, e não um print da página web. O visualizador do in.gov.br o serve
#: por (jornal, data, página); o "jornal" é o código da seção no acervo, e o
#: código de autenticidade impresso no rodapé confirma a composição:
#: `0530|20260622|0007|D` = seção 3 · 22/06/2026 · página 7 · dígito.
JORNAIS = {"do1": "515", "do2": "529", "do3": "530"}
VIEWER_PDF = "https://pesquisa.in.gov.br/imprensa/servlet/INPDFViewer"

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
    pagina: str | None = None
    url: str | None = None
    #: PDF certificado da página do jornal (o que se anexa ao processo)
    pdf_url: str | None = None
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


_RE_PDF = re.compile(r"https?://\S+?\.pdf|https?://\S*INPDFViewer\S*", re.I)


def jornal_de(secao: Any) -> str | None:
    """Código do jornal no acervo a partir da seção ("DO3", "do3", "Seção 3")."""
    plano = normalizar(secao)
    if not plano:
        return None
    for chave, codigo in JORNAIS.items():
        if chave in plano.replace(" ", "") or f"secao {chave[-1]}" in plano:
            return codigo
    return None


def url_pdf(secao: Any, data: date | None, pagina: Any) -> str | None:
    """A URL do PDF certificado — só quando os TRÊS dados existem.

    Página é o que muda entre uma matéria e outra da mesma edição: sem ela a URL
    montada abriria uma página qualquer do jornal daquele dia e o gestor
    anexaria ao processo o extrato de outro município. Sem certeza, sem link.
    """
    jornal = jornal_de(secao)
    numero = re.sub(r"\D", "", str(pagina or ""))
    if not jornal or not data or not numero:
        return None
    return (
        f"{VIEWER_PDF}?jornal={jornal}&pagina={int(numero)}"
        f"&data={data.strftime('%d/%m/%Y')}&captchafield=firstAccess"
    )


def _pdf_publicado(item: dict) -> str | None:
    """URL de PDF que a PRÓPRIA fonte publicou no resultado (vence a montada)."""
    for valor in item.values():
        if isinstance(valor, str) and (m := _RE_PDF.search(valor)):
            return m.group(0)
    return None


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
        quando = _data(_primeiro(item, "pubDate", "editionDate", "date"))
        secao = str(_primeiro(item, "pubName", "section") or "") or None
        pagina_jornal = _primeiro(item, "numberPage", "pageNumber", "page")
        pagina_jornal = str(pagina_jornal) if pagina_jornal is not None else None
        saida.append(
            Publicacao(
                titulo=_texto(str(_primeiro(item, "title", "artType") or "")),
                texto=_texto(str(_primeiro(item, "content", "abstract", "text") or "")),
                data=quando,
                edicao=str(_primeiro(item, "editionNumber", "edition") or "") or None,
                secao=secao,
                pagina=pagina_jornal,
                url=_url(item),
                pdf_url=_pdf_publicado(item) or url_pdf(secao, quando, pagina_jornal),
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


# ── o PDF certificado ──────────────────────────────────────────────────────
#: teto do download. A página do DOU tem centenas de KB; o teto existe para que
#: uma resposta inesperada (o portal servindo a edição inteira, ou um HTML de
#: erro gigante) não vire consumo de memória no worker da API.
MAX_PDF_BYTES = 25 * 1024 * 1024

_SECAO_NOME = {"515": "secao1", "529": "secao2", "530": "secao3"}


def nome_arquivo_pdf(secao: Any, data: date | None, pagina: Any) -> str:
    """Nome legível para o arquivo baixado — o gestor anexa isto ao processo."""
    partes = ["dou"]
    if (jornal := jornal_de(secao)) and (nome := _SECAO_NOME.get(jornal)):
        partes.append(nome)
    if data:
        partes.append(data.strftime("%Y-%m-%d"))
    if numero := re.sub(r"\D", "", str(pagina or "")):
        partes.append(f"pagina-{int(numero)}")
    return "-".join(partes) + ".pdf"


def e_pdf(conteudo: bytes, content_type: str | None) -> bool:
    """O corpo é MESMO um PDF?

    O visualizador do in.gov.br responde 200 com HTML quando cai no captcha ou
    na página de erro. Entregar isso ao gestor com extensão `.pdf` seria pior
    que falhar: ele anexaria ao processo um arquivo que não abre. A assinatura
    `%PDF` no início é o teste que não depende do header.
    """
    if conteudo[:5].startswith(b"%PDF"):
        return True
    return bool(content_type and "application/pdf" in content_type.lower())


async def baixar_pdf(url: str) -> bytes:
    """Baixa o PDF certificado da fonte.

    Sem persistir nada: o Hub só faz a ponte, para o gestor não precisar
    atravessar o captcha do visualizador. Falha vira `DouIndisponivel` com a
    razão — a tela cai para o link direto, que continua valendo.
    """
    if not url:
        raise DouIndisponivel("esta publicação não tem PDF certificado resolvido")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={**_CABECALHOS, "Accept": "application/pdf"})
    except httpx.TransportError as exc:
        raise DouIndisponivel(f"não foi possível alcançar o Diário Oficial: {exc}") from exc
    if resp.status_code >= 400:
        raise DouIndisponivel(f"o Diário Oficial respondeu {resp.status_code}")
    conteudo = resp.content
    if len(conteudo) > MAX_PDF_BYTES:
        raise DouIndisponivel("o arquivo devolvido pelo Diário Oficial é grande demais")
    if not e_pdf(conteudo, resp.headers.get("content-type")):
        raise DouIndisponivel(
            "o Diário Oficial devolveu uma página em vez do PDF "
            "(o visualizador pode estar pedindo verificação) — abra o link direto"
        )
    return conteudo
