"""Extrator das transferências do Transferegov (painel Qlik público do SERPRO).

O painel é Qlik Sense. O Engine API direto recusa sessão anônima (WebSocket 403),
mas um navegador real ativa a sessão sozinho. Então abrimos a página com Playwright
e pedimos os dados via Capability API (`js/qlik`) já carregada nela.

A tabela "Relatório Geral das Transferências" é o objeto `pRTCg` do app
`5cc78f2a-...`. Filtramos pelo campo `Município` (e opcionalmente `Ano`) e lemos o
hipercubo paginado — cada linha é uma OPORTUNIDADE.

Rodar como serviço SEPARADO (Chromium é pesado; a VPS de produção tem memória
limitada e não pode competir com o container `api`). concurrency=1.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

PANEL_URL = (
    "https://dd-publico.serpro.gov.br/extensions/painel/TransferegovbrVisaoGeral.html"
)
APP_ID = "5cc78f2a-d402-423b-a056-6085f0da9d3e"
TABLE_OBJECT_ID = "pRTCg"  # "Relatório Geral das Transferências"
FIELD_MUNICIPIO = "Município"
FIELD_ANO = "Ano"

# Nomes das colunas na ordem em que o hipercubo as devolve (dims + medidas).
# Fixados aqui para virarem chaves estáveis no banco, independentes do rótulo
# que o Qlik mostrar. Ordem confirmada no qLayout do objeto pRTCg.
COLUMNS = [
    "nr_transferencia",
    "link",
    "ano",
    "situacao",
    "tipo_transferencia",
    "modalidade_transferencia",
    "orgao_repassador",
    "cnpj_recebedor",
    "ente_recebedor",
    "natureza_juridica",
    "uf",
    "municipio",
    "data_assinatura",
    "data_inicio_vigencia",
    "data_fim_vigencia",
    "objeto",
    # medidas
    "qtd_transferencias",
    "valor_global",
    "valor_empenhado",
    "valor_liberado",
    "valor_pago",
    "saldo_em_conta",
]

PAGE_HEIGHT = 200  # linhas por página do getHyperCubeData


@dataclass
class ExtractResult:
    municipio: str
    ano: str | None
    total: int
    rows: list[dict] = field(default_factory=list)
    error: str | None = None


# `pRTCg` é uma extensão custom: o hipercubo só se popula quando o objeto RENDERIZA
# (exportData/enigma cru veem vazio). Então forçamos o render num container off-screen
# via `app.getObject`; o próprio código da extensão dispara os GetHyperCubeData, cujas
# respostas capturamos pelos frames do WebSocket (page.on('websocket')).
_RENDER_JS = """
async ([appId, objId, muni, ano, fMuni, fAno]) => {
  const qlik = await new Promise((res) => require(["js/qlik"], res));
  const app = qlik.openApp(appId, {});
  try { app.field(fMuni).selectValues([muni], false, true); } catch (e) {}
  if (ano) { try { app.field(fAno).selectValues([Number(ano) || ano], false, true); } catch (e) {} }
  await new Promise((r) => setTimeout(r, 3500));

  // container alto para a extensão pedir muitas linhas de uma vez
  let el = document.getElementById("__grab");
  if (!el) {
    el = document.createElement("div");
    el.id = "__grab";
    el.style.cssText = "position:absolute;left:-9999px;top:0;width:1400px;height:6000px;";
    document.body.appendChild(el);
  }
  app.getObject(el, objId);
  return { started: true };
}
"""


def _rows_from_frames(frames: list[str], obj_id: str) -> tuple[int, list[list[str]]]:
    """Junta as linhas (qMatrix) dos frames do objeto, deduplicando por qTop."""
    import json as _json

    total = 0
    pages: dict[int, list] = {}

    def visit(node, top_hint=0):
        nonlocal total
        if isinstance(node, dict):
            if "qHyperCube" in node:
                hc = node["qHyperCube"]
                if isinstance(hc.get("qSize"), dict):
                    total = max(total, hc["qSize"].get("qcy", 0))
                for dp in hc.get("qDataPages", []) or []:
                    t = (dp.get("qArea") or {}).get("qTop", top_hint)
                    m = [[c.get("qText", "") for c in r] for r in dp.get("qMatrix", [])]
                    if m:
                        pages[t] = m
            for v in node.values():
                visit(v, top_hint)
        elif isinstance(node, list):
            for v in node:
                visit(v, top_hint)

    for f in frames:
        if not isinstance(f, str) or obj_id not in f or "qMatrix" not in f:
            continue
        try:
            visit(_json.loads(f))
        except Exception:  # noqa: BLE001
            continue

    rows: list[list[str]] = []
    for top in sorted(pages):
        rows.extend(pages[top])
    return total or len(rows), rows


def _parse_csv(text: str) -> list[dict]:
    """Converte o CSV exportado pelo Qlik em dicts com as chaves estáveis de COLUMNS.

    O Qlik exporta com cabeçalho (rótulos dele) na 1ª linha; ignoramos os rótulos
    e mapeamos POSICIONALMENTE para COLUMNS — a ordem é a do objeto pRTCg.
    """
    import csv
    import io

    rows: list[dict] = []
    reader = csv.reader(io.StringIO(text))
    for i, cells in enumerate(reader):
        if i == 0 or not any(cells):  # pula cabeçalho e linhas vazias
            continue
        row = {COLUMNS[j]: cells[j] for j in range(min(len(COLUMNS), len(cells)))}
        rows.append(row)
    return rows


async def extract(
    municipio: str,
    ano: str | None = None,
    *,
    headless: bool = True,
    timeout_ms: int = 90_000,
) -> ExtractResult:
    """Extrai a tabela de transferências de um município (opcionalmente por ano)."""
    frames: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page()
            page.set_default_timeout(timeout_ms)

            def on_ws(ws):
                ws.on("framereceived", lambda payload: frames.append(payload))

            page.on("websocket", on_ws)

            # domcontentloaded é confiável; networkidle trava nesse painel pesado
            await page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_function("() => typeof require === 'function'", timeout=timeout_ms)
            await page.wait_for_timeout(8000)  # engine conecta + painel monta

            # aplica a seleção e força o render do objeto (via getObject + rolagem)
            await page.evaluate(
                _RENDER_JS, [APP_ID, TABLE_OBJECT_ID, municipio, ano, FIELD_MUNICIPIO, FIELD_ANO]
            )
            # rola o painel até o fim (a tabela do rodapé é lazy) e pagina
            for _ in range(6):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(2500)
        except Exception as exc:  # noqa: BLE001
            await browser.close()
            return ExtractResult(municipio, ano, 0, error=str(exc))
        await browser.close()

    total, raw_rows = _rows_from_frames(frames, TABLE_OBJECT_ID)
    rows = [
        {COLUMNS[j]: cells[j] for j in range(min(len(COLUMNS), len(cells)))}
        for cells in raw_rows
    ]
    return ExtractResult(municipio=municipio, ano=ano, total=total, rows=rows)


if __name__ == "__main__":  # smoke test manual: python -m extractor "Fortaleza" 2026
    import json
    import sys

    muni = sys.argv[1] if len(sys.argv) > 1 else "Fortaleza"
    ano = sys.argv[2] if len(sys.argv) > 2 else None
    r = asyncio.run(extract(muni, ano))
    print(json.dumps(
        {"municipio": r.municipio, "ano": r.ano, "total": r.total,
         "erro": r.error, "amostra": r.rows[:3]},
        ensure_ascii=False, indent=2,
    ))
