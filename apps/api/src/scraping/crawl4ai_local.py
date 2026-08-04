"""Provider Crawl4AI em modo BIBLIOTECA (in-process, sem servidor).

Complementa `scraping/crawl4ai.py`, que fala com um servidor Crawl4AI remoto:
aqui a mesma engine roda dentro da API (`pip install crawl4ai`), então não há
container extra para subir nem base URL para configurar. É o caminho preferido
quando ninguém provisionou infraestrutura de scraping — que é o estado normal de
uma instalação nova.

O que ele traz além do Playwright cru (`scraping/playwright.py`): markdown já
limpo do conteúdo principal (o "fit markdown", que descarta menu/rodapé) e a
estratégia de extração por CSS do próprio Crawl4AI. A extração aqui segue
DETERMINÍSTICA e sem LLM — as páginas das nossas duas fontes são tabulares, e o
mapeamento tabela → schema do connector é reaproveitado de
`scraping/playwright.py`, para os dois providers responderem no mesmo formato.

Provider-opcional como os demais: sem o pacote instalado (extra `scraping`) ou
com `scraping_crawl4ai_local` = "off" no painel, `is_enabled()` é False e o
facade nem o inclui na rodada.
"""

from __future__ import annotations

import re
from typing import Any

from ..services import config as config_service
from .tabelas import alvo_do_schema, linhas_de_html, maior_tabela, mapear

# O Crawl4AI orquestra o browser; a espera cobre o painel Qlik montar o grid.
PAGE_TIMEOUT_MS = 60_000
ESPERA_POS_RENDER_MS = 2_500

#: rola a página para vencer grid virtualizado antes de ler o HTML
JS_ROLAR = """
(async () => {
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 25; i++) {
    const roláveis = Array.from(document.querySelectorAll('*')).filter((el) => {
      const s = getComputedStyle(el);
      return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 40;
    });
    roláveis.sort((a, b) => b.scrollHeight - a.scrollHeight);
    if (roláveis[0]) roláveis[0].scrollTop += roláveis[0].clientHeight;
    window.scrollBy(0, window.innerHeight);
    await dormir(350);
  }
})();
"""


class Crawl4aiLocalNotConfigured(RuntimeError):
    """Pacote `crawl4ai` ausente ou provider desligado no painel."""


def _tem_crawl4ai() -> bool:
    try:
        import crawl4ai  # noqa: F401
    except Exception:
        return False
    return True


class Crawl4aiLocalClient:
    def __init__(self, habilitado: bool | None = None) -> None:
        self._habilitado_override = habilitado

    async def is_enabled(self) -> bool:
        if self._habilitado_override is not None:
            return self._habilitado_override
        if not _tem_crawl4ai():
            return False
        try:
            valor = await config_service.resolver("scraping_crawl4ai_local")
        except Exception:
            valor = None
        return (valor or "on").strip().lower() not in {"off", "false", "0", "nao", "não"}

    async def _require(self) -> None:
        if not await self.is_enabled():
            raise Crawl4aiLocalNotConfigured(
                "Crawl4AI local indisponível — instale o extra 'scraping' "
                "(uv sync --extra scraping) ou ligue 'scraping_crawl4ai_local' no painel"
            )

    async def _rodar(self, url: str) -> Any:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

        browser = BrowserConfig(headless=True, extra_args=["--no-sandbox"])
        run = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,  # dado público muda a cada dia: nunca servir cache
            page_timeout=PAGE_TIMEOUT_MS,
            delay_before_return_html=ESPERA_POS_RENDER_MS / 1000,
            js_code=[JS_ROLAR],
            scan_full_page=True,
        )
        async with AsyncWebCrawler(config=browser) as crawler:
            resultado = await crawler.arun(url=url, config=run)

        # O Crawl4AI NÃO levanta em falha de navegação: devolve success=False.
        # Deixar passar transformaria "não consegui abrir a página" em "a fonte
        # não tem registros" — mentira que o gestor veria como painel vazio.
        # Levantando, o serviço registra o incidente em `sync_runs`.
        if not getattr(resultado, "success", True):
            erro = getattr(resultado, "error_message", "") or "falha ao carregar a página"
            raise RuntimeError(f"Crawl4AI não abriu {url}: {erro}")
        return resultado

    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        await self._require()
        resultado = await self._rodar(url)
        markdown = getattr(resultado, "markdown", "") or ""
        # versões recentes devolvem um objeto com fit_markdown/raw_markdown
        texto = (
            getattr(markdown, "fit_markdown", None)
            or getattr(markdown, "raw_markdown", None)
            or str(markdown)
        )
        return {
            "markdown": texto,
            "html": getattr(resultado, "cleaned_html", None) or getattr(resultado, "html", ""),
            "tabelas": _tabelas_do_resultado(resultado),
        }

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        """Tabelas da página → objeto no formato do schema do connector."""
        await self._require()
        resultado = await self._rodar(url)
        linhas = maior_tabela(_tabelas_do_resultado(resultado))
        chave, campos = alvo_do_schema(schema)
        if not chave:
            return {}
        return {chave: [mapear(linha, campos) for linha in linhas]}

    async def health_check(self) -> bool:
        return await self.is_enabled()


def _tabelas_do_resultado(resultado: Any) -> list[list[dict[str, str]]]:
    """Tabelas do Crawl4AI (`result.tables`) → linhas cabeçalho→célula.

    O Crawl4AI entrega `{headers: [...], rows: [[...]]}`; quando a versão
    instalada não expõe `tables`, cai para o HTML tabular do markdown.
    """
    tabelas = getattr(resultado, "tables", None) or []
    saida: list[list[dict[str, str]]] = []
    for tabela in tabelas:
        cabecalhos = [str(h).strip() for h in (tabela.get("headers") or [])]
        linhas = tabela.get("rows") or []
        registros = []
        for linha in linhas:
            celulas = [str(c).strip() for c in linha]
            if not any(celulas):
                continue
            registros.append(
                {
                    (cabecalhos[i] if i < len(cabecalhos) and cabecalhos[i] else f"col_{i}"): valor
                    for i, valor in enumerate(celulas)
                }
            )
        if registros:
            saida.append(registros)
    if saida:
        return saida
    # `result.tables` só enxerga <table>; o grid ARIA do painel Qlik vem do HTML
    html = getattr(resultado, "html", None) or getattr(resultado, "cleaned_html", "") or ""
    do_html = linhas_de_html(html)
    if do_html:
        return do_html
    return _tabelas_do_markdown(getattr(resultado, "markdown", "") or "")


def _tabelas_do_markdown(markdown: Any) -> list[list[dict[str, str]]]:
    """Fallback: tabela em pipe-markdown → linhas cabeçalho→célula."""
    texto = (
        getattr(markdown, "raw_markdown", None)
        or getattr(markdown, "fit_markdown", None)
        or str(markdown)
    )
    blocos: list[list[dict[str, str]]] = []
    atual: list[list[str]] = []
    for linha in texto.splitlines():
        crua = linha.strip()
        if crua.startswith("|") and crua.endswith("|"):
            celulas = [c.strip() for c in crua.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "") for c in celulas):
                continue  # linha separadora do markdown
            atual.append(celulas)
            continue
        if atual:
            blocos.append(_bloco_para_registros(atual))
            atual = []
    if atual:
        blocos.append(_bloco_para_registros(atual))
    return [b for b in blocos if b]


def _bloco_para_registros(bloco: list[list[str]]) -> list[dict[str, str]]:
    if len(bloco) < 2:
        return []
    cabecalhos = bloco[0]
    return [
        {
            (cabecalhos[i] if i < len(cabecalhos) and cabecalhos[i] else f"col_{i}"): valor
            for i, valor in enumerate(linha)
        }
        for linha in bloco[1:]
        if any(linha)
    ]


def get_crawl4ai_local() -> Crawl4aiLocalClient:
    return Crawl4aiLocalClient()


__all__ = ["Crawl4aiLocalClient", "Crawl4aiLocalNotConfigured", "get_crawl4ai_local"]
