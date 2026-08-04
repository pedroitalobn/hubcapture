"""Provider de scraping LOCAL — Chromium headless via Playwright.

Por que existe: as duas fontes da v1 dependem de páginas que só existem depois
que o JavaScript roda — o painel da Visão Geral do TransfereGov (Qlik, hospedado
em dd-publico.serpro.gov.br) e a consulta do FNS. Os outros providers do facade
dependem de infraestrutura externa (servidor Crawl4AI) ou de chave paga
(Firecrawl); enquanto nenhum dos dois está plugado, o Hub não extrai NADA dessas
páginas. Este provider fecha esse buraco rodando o browser no próprio container:
sem credencial, sem serviço externo, sem custo por página.

Extração sem LLM, de propósito: o dado dessas páginas é TABULAR. O provider lê
tanto `<table>` clássica quanto **grid ARIA** (`role="grid"`/`role="row"`/
`role="columnheader"`), que é como o Qlik renderiza — e resolve a virtualização
rolando o grid até parar de aparecer linha nova. As linhas viram `list[dict]`
(cabeçalho → célula) e são mapeadas ao JSON Schema que o connector já declara,
casando cabeçalho com propriedade por palavra-chave sem acento. Determinístico e
sem custo de token; quando a página não é tabular, `scrape()` devolve o texto e
o caminho por LLM dos outros providers segue disponível.

Provider-opcional, no mesmo contrato dos demais: sem o pacote `playwright`
instalado (extra `scraping`) ou com `scraping_playwright` = "off" no painel,
`is_enabled()` é False e o facade simplesmente não o inclui na rodada.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..services import config as config_service
from .tabelas import alvo_do_schema, maior_tabela, mapear

# Argumentos obrigatórios em container (sem sandbox de usuário, /dev/shm pequeno).
ARGS_CHROMIUM = ["--no-sandbox", "--disable-dev-shm-usage"]

# Chromium do sistema, usado quando o browser que acompanha o Playwright não
# está baixado (imagem que já traz o browser, build divergente do pacote…).
# Env vence, porque é o que o Dockerfile/hospedagem consegue apontar.
ENV_EXECUTAVEL = ("CHROMIUM_EXECUTABLE_PATH", "CHROMIUM_PATH", "PLAYWRIGHT_CHROMIUM_EXECUTABLE")
CAMINHOS_CHROMIUM = (
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


def _executavel_do_sistema() -> str | None:
    for var in ENV_EXECUTAVEL:
        caminho = os.environ.get(var)
        if caminho and os.path.exists(caminho):
            return caminho
    return next((c for c in CAMINHOS_CHROMIUM if os.path.exists(c)), None)


# Navegação: o painel Qlik demora para montar o grid; margem generosa mas finita.
NAV_TIMEOUT_MS = 60_000
REDE_OCIOSA_MS = 15_000
ESPERA_POS_RENDER_MS = 2_500

# Virtualização: quantas rodadas de rolagem tentamos antes de desistir e
# quantas rodadas seguidas sem linha nova bastam para considerar o fim.
MAX_ROLAGENS = 40
ROLAGENS_SEM_NOVIDADE = 3
ESPERA_ROLAGEM_MS = 450

SELETOR_GRID = "table, [role='grid'], [role='table']"


class PlaywrightNotConfigured(RuntimeError):
    """Playwright indisponível (pacote ausente ou desligado no painel)."""


def _tem_playwright() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except Exception:
        return False
    return True


class PlaywrightClient:
    """Renderiza a página no Chromium local e extrai as tabelas/grids."""

    def __init__(self, habilitado: bool | None = None) -> None:
        self._habilitado_override = habilitado

    async def is_enabled(self) -> bool:
        if self._habilitado_override is not None:
            return self._habilitado_override
        if not _tem_playwright():
            return False
        try:
            valor = await config_service.resolver("scraping_playwright")
        except Exception:
            valor = None
        return (valor or "on").strip().lower() not in {"off", "false", "0", "nao", "não"}

    async def _require(self) -> None:
        if not await self.is_enabled():
            raise PlaywrightNotConfigured(
                "Playwright indisponível — instale o extra 'scraping' "
                "(uv sync --extra scraping) ou ligue 'scraping_playwright' no painel"
            )

    # ── Renderização ────────────────────────────────────────────────────────
    async def _render(self, url: str) -> tuple[str, str, list[list[dict[str, str]]]]:
        """Abre a URL e devolve (texto, html, tabelas)."""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(args=ARGS_CHROMIUM)
            except Exception:
                # browser do pacote ausente/divergente → Chromium do sistema
                executavel = _executavel_do_sistema()
                if not executavel:
                    raise
                browser = await pw.chromium.launch(args=ARGS_CHROMIUM, executable_path=executavel)
            try:
                pagina = await browser.new_page(locale="pt-BR")
                pagina.set_default_timeout(NAV_TIMEOUT_MS)
                await pagina.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                # o grid do Qlik só existe depois das chamadas XHR do painel
                try:
                    await pagina.wait_for_load_state("networkidle", timeout=REDE_OCIOSA_MS)
                except Exception:
                    pass  # rede que nunca fica ociosa (polling) não invalida a página
                try:
                    await pagina.wait_for_selector(SELETOR_GRID, timeout=REDE_OCIOSA_MS)
                except Exception:
                    pass  # página sem grid ainda serve para scrape() de texto
                await pagina.wait_for_timeout(ESPERA_POS_RENDER_MS)

                await self._rolar_ate_o_fim(pagina)

                texto = await pagina.evaluate("() => document.body?.innerText ?? ''")
                html = await pagina.content()
                tabelas = await pagina.evaluate(_JS_EXTRAIR_TABELAS)
                return texto, html, tabelas
            finally:
                await browser.close()

    async def _rolar_ate_o_fim(self, pagina: Any) -> None:
        """Vence a virtualização: rola o grid enquanto surgirem linhas novas."""
        anterior, estaveis = -1, 0
        for _ in range(MAX_ROLAGENS):
            total = await pagina.evaluate(_JS_CONTAR_LINHAS)
            if total == anterior:
                estaveis += 1
                if estaveis >= ROLAGENS_SEM_NOVIDADE:
                    return
            else:
                estaveis = 0
            anterior = total
            await pagina.evaluate(_JS_ROLAR)
            await pagina.wait_for_timeout(ESPERA_ROLAGEM_MS)

    # ── Contrato do facade ──────────────────────────────────────────────────
    async def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        await self._require()
        texto, html, tabelas = await self._render(url)
        return {"markdown": texto, "html": html, "tabelas": tabelas}

    async def extract(
        self, url: str, schema: dict[str, Any], prompt: str | None = None
    ) -> dict[str, Any]:
        """Tabelas renderizadas → objeto no formato do schema do connector."""
        await self._require()
        texto, _html, tabelas = await self._render(url)
        linhas = maior_tabela(tabelas)
        chave, campos = alvo_do_schema(schema)
        if not chave:
            return {}
        itens = [mapear(linha, campos) for linha in linhas]
        return {chave: itens, "_texto": texto}

    async def health_check(self) -> bool:
        return await self.is_enabled()


# ── JS injetado na página ───────────────────────────────────────────────────
# Um só coletor para <table> e para grid ARIA (Qlik): pega os cabeçalhos da
# primeira linha (th/columnheader, com fallback para a 1ª linha de células) e
# devolve cada linha como objeto cabeçalho → texto.
_JS_EXTRAIR_TABELAS = """
() => {
  const txt = (el) => (el?.innerText ?? '').replace(/\\s+/g, ' ').trim();
  const linhasDe = (raiz) =>
    Array.from(raiz.querySelectorAll('tr, [role="row"]'));
  const SEL_CELULA =
    'th, td, [role="columnheader"], [role="gridcell"], [role="cell"]';
  const celulasDe = (linha) => Array.from(linha.querySelectorAll(SEL_CELULA));

  const saida = [];
  const grids = Array.from(document.querySelectorAll('table, [role="grid"], [role="table"]'));
  for (const grid of grids) {
    const linhas = linhasDe(grid);
    if (linhas.length < 2) continue;
    let cabecalhos = celulasDe(linhas[0]).map(txt);
    let inicio = 1;
    if (cabecalhos.every((c) => !c)) { continue; }
    const registros = [];
    for (let i = inicio; i < linhas.length; i++) {
      const celulas = celulasDe(linhas[i]).map(txt);
      if (!celulas.length || celulas.every((c) => !c)) continue;
      const obj = {};
      celulas.forEach((valor, j) => {
        const chave = cabecalhos[j] || `col_${j}`;
        if (chave) obj[chave] = valor;
      });
      registros.push(obj);
    }
    if (registros.length) saida.push(registros);
  }
  return saida;
}
"""

_JS_CONTAR_LINHAS = """
() => document.querySelectorAll('tr, [role="row"]').length
"""

# Rola o container rolável mais alto (o grid virtualizado) e também a janela —
# cobre tanto grid com scroll interno quanto página com scroll normal.
_JS_ROLAR = """
() => {
  const roláveis = Array.from(document.querySelectorAll('*')).filter((el) => {
    const s = getComputedStyle(el);
    return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 40;
  });
  roláveis.sort((a, b) => b.scrollHeight - a.scrollHeight);
  if (roláveis[0]) roláveis[0].scrollTop = roláveis[0].scrollTop + roláveis[0].clientHeight;
  window.scrollBy(0, window.innerHeight);
}
"""


def get_playwright() -> PlaywrightClient:
    return PlaywrightClient()


__all__ = ["PlaywrightClient", "PlaywrightNotConfigured", "get_playwright"]


async def _amain(url: str) -> None:  # pragma: no cover — uso manual
    dados = await PlaywrightClient(habilitado=True).scrape(url)
    print(dados["markdown"][:2000])


if __name__ == "__main__":  # pragma: no cover
    import sys

    asyncio.run(_amain(sys.argv[1]))
