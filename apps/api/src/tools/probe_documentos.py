"""Probe dos documentos digitalizados de UMA proposta — a página real, linha a linha.

"Nem todos os documentos estão disponíveis para download": para responder POR QUÊ
é preciso ver o que a página do SIconv realmente tem em cada linha — o texto das
células, os hrefs, as ações nos scripts, os ids — e confrontar com o que o parser
entendeu. O sandbox de CI/agente não alcança o gov.br; este probe roda de uma
máquina que alcança e devolve a evidência que calibra `parse_documentos`.

    cd apps/api
    uv run python -m src.tools.probe_documentos 123456
    uv run python -m src.tools.probe_documentos 123456 --baixar
    uv run python -m src.tools.probe_documentos 123456 --salvar /tmp/siconv --json

`--baixar` tenta a PONTE em cada documento com endereço e relata, por arquivo, o
que a fonte devolveu (status, tipo, tamanho, nome) ou por que recusou. `--salvar`
grava o HTML da página (e das páginas do paginador) no diretório — é o que se
anexa ao chamado quando o layout mudou. Sai com código 1 quando a lista veio
vazia ou algum download falhou.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ..connectors import pareceres_siconv as siconv


async def _sondar(id_proposta: str, *, baixar: bool, salvar: Path | None) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    saida: dict[str, Any] = {"id_proposta": id_proposta, "status": "ok"}
    detalhe = f"{siconv.DETALHE}?idProposta={id_proposta}&destino=&idConvenio="
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            pg = await (await browser.new_context(locale="pt-BR")).new_page()
            await pg.goto(siconv.ENTRADA, wait_until="networkidle", timeout=siconv.TIMEOUT_MS)
            await pg.goto(detalhe, wait_until="networkidle", timeout=siconv.TIMEOUT_MS)
            titulo = await pg.title()
            saida["titulo"] = titulo
            if "Login" in titulo:
                saida["status"] = "erro"
                saida["erro"] = "caiu na tela de login — o rito do acesso livre mudou"
                return saida
            pagina = await pg.content()
            if salvar:
                salvar.mkdir(parents=True, exist_ok=True)
                (salvar / f"proposta_{id_proposta}.html").write_text(pagina, encoding="utf-8")
            saida["marca_documentos"] = bool(siconv._MARCA_DOCUMENTOS.search(pagina))
            saida["linhas_brutas"] = siconv.linhas_brutas_documentos(pagina)
            saida["paginacao"] = siconv.links_de_paginacao(pagina)
            conector = siconv.get_connector()
            docs = await conector._documentos_completos(pg, pagina)
            saida["documentos"] = docs
            if salvar:
                for i, url in enumerate(saida["paginacao"], start=2):
                    try:
                        await pg.goto(url, wait_until="networkidle", timeout=siconv.TIMEOUT_MS)
                        (salvar / f"proposta_{id_proposta}_pagina{i}.html").write_text(
                            await pg.content(), encoding="utf-8"
                        )
                    except Exception as exc:  # noqa: BLE001 — probe segue
                        saida.setdefault("avisos", []).append(f"página {url}: {exc}")
            if baixar:
                # volta à proposta: a ação de download exige a "proposta corrente"
                await pg.goto(detalhe, wait_until="networkidle", timeout=siconv.TIMEOUT_MS)
                resultados = []
                for d in docs:
                    item = {
                        "nome": d["nome"],
                        "url": d.get("url"),
                        "derivada": bool(d.get("_url_derivada")),
                    }
                    if not d.get("url"):
                        item["resultado"] = "sem endereço na página"
                    elif not siconv.e_url_da_fonte(d["url"]):
                        item["resultado"] = "endereço fora do portal — a ponte recusa (SSRF)"
                    else:
                        try:
                            conteudo, tipo, nome = await conector._requisitar_arquivo(
                                pg, d["url"], detalhe
                            )
                            item["resultado"] = "ok"
                            item["bytes"] = len(conteudo)
                            item["content_type"] = tipo
                            item["nome_declarado"] = nome
                            item["assinatura"] = conteudo[:8].hex()
                        except Exception as exc:  # noqa: BLE001 — é o que se quer ver
                            item["resultado"] = f"{type(exc).__name__}: {exc}"
                    resultados.append(item)
                saida["downloads"] = resultados
        finally:
            await browser.close()
    return saida


def _imprimir(r: dict[str, Any]) -> None:
    print(f"proposta {r['id_proposta']} — título da página: {r.get('titulo')!r}")
    if r.get("erro"):
        print(f"  ERRO: {r['erro']}")
        return
    print(f"  seção 'Documentos Digitalizados' encontrada: {r['marca_documentos']}")
    print(f"  linhas na seção: {len(r['linhas_brutas'])}")
    for i, linha in enumerate(r["linhas_brutas"], start=1):
        print(f"   [{i}] células: {linha['celulas']}")
        if linha["hrefs"]:
            print(f"        hrefs: {linha['hrefs']}")
        if linha["acoes_js"]:
            print(f"        ações js: {linha['acoes_js']}")
        if linha["ids"]:
            print(f"        ids: {linha['ids']}")
    print(f"  links de paginação: {r['paginacao'] or 'nenhum'}")
    print(f"  documentos reconhecidos: {len(r['documentos'])}")
    for d in r["documentos"]:
        marca = " (url DERIVADA do id)" if d.get("_url_derivada") else ""
        data = d.get("data_upload") or "sem data"
        print(f"   - {d['nome']} · {data} · {d.get('url') or 'SEM LINK'}{marca}")
    for item in r.get("downloads", []):
        extra = (
            f" · {item['bytes']} bytes · {item.get('content_type')} · {item.get('nome_declarado')}"
            if item["resultado"] == "ok"
            else ""
        )
        print(f"   ⤓ {item['nome']}: {item['resultado']}{extra}")
    for aviso in r.get("avisos", []):
        print(f"  aviso: {aviso}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "id_proposta",
        help="idProposta INTERNO do SIconv (numérico; é o id_externo das cargas do pacote)",
    )
    ap.add_argument(
        "--baixar", action="store_true", help="tenta a ponte de download em cada documento"
    )
    ap.add_argument(
        "--salvar", type=Path, default=None, help="diretório para gravar o HTML das páginas"
    )
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    args = ap.parse_args(argv)
    if not str(args.id_proposta).strip().isdigit():
        print("o idProposta precisa ser numérico (o id interno do SIconv)", file=sys.stderr)
        return 2
    r = asyncio.run(_sondar(str(args.id_proposta).strip(), baixar=args.baixar, salvar=args.salvar))
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        _imprimir(r)
    falhou = (
        r.get("status") != "ok"
        or not r.get("documentos")
        or any(x["resultado"] != "ok" for x in r.get("downloads", []))
    )
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
