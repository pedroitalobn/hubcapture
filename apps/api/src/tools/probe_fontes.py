"""Probe das fontes — bate nas APIs/páginas REAIS e relata o que cada uma devolve.

Existe porque calibrar connector contra fonte de governo é trabalho empírico: a
rota muda, a coluna de IBGE tem outro nome, o painel troca o rótulo da coluna. Em
vez de descobrir isso pelo `sync_runs` depois do deploy, roda-se isto e vê-se na
hora, fonte por fonte: respondeu? quantos registros? que campos vieram?

Não precisa de banco nem de API no ar: usa só os connectors e o resolver de
configuração (que cai no `.env` quando o Postgres não responde).

    cd apps/api
    uv run python -m src.tools.probe_fontes 3550308          # todas as habilitadas
    uv run python -m src.tools.probe_fontes 3550308 --fonte fns
    uv run python -m src.tools.probe_fontes 3550308 --json    # saída p/ arquivo

Sai com código 1 se alguma fonte falhar — dá para usar em verificação de deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..connectors import base as connectors_base  # noqa: F401  (registra os connectors)
from ..connectors.base import get_connector
from ..services import fontes as fontes_service

# Import com efeito colateral: cada módulo registra sua instância no registry.
from ..connectors import (  # noqa: F401  isort:skip
    fns,
    serpro,
    transferegov_disc,
    transferegov_esp,
    transferegov_ff,
    transferegov_voluntarias,
)

TIMEOUT_PADRAO = 180.0
DIAS_PADRAO = 365


async def _probe(fonte: str, ibge: str, since: date, timeout: float) -> dict[str, Any]:
    inicio = datetime.now(UTC)
    resultado: dict[str, Any] = {"fonte": fonte, "grupo": fontes_service.grupo_de(fonte)}
    try:
        connector = get_connector(fonte)
    except KeyError as exc:
        return {**resultado, "status": "erro", "erro": str(exc)}

    try:
        resultado["health_check"] = await asyncio.wait_for(
            connector.health_check(), timeout=timeout
        )
    except Exception as exc:
        resultado["health_check"] = False
        resultado["health_erro"] = f"{type(exc).__name__}: {exc}"

    try:
        registros = await asyncio.wait_for(connector.collect(ibge, since=since), timeout=timeout)
        resultado["status"] = "ok" if registros else "vazio"
        resultado["registros"] = len(registros)
        if registros:
            amostra = registros[0]
            resultado["id_externo"] = amostra.id_externo
            resultado["endpoint"] = amostra.endpoint
            resultado["campos"] = sorted(_campos(amostra.raw))
            resultado["amostra"] = _resumir(amostra.raw)
    except TimeoutError:
        resultado["status"] = "timeout"
        resultado["erro"] = f"coleta passou de {timeout:.0f}s"
    except Exception as exc:
        resultado["status"] = "erro"
        resultado["erro"] = f"{type(exc).__name__}: {exc}"

    resultado["segundos"] = round((datetime.now(UTC) - inicio).total_seconds(), 1)
    return resultado


def _campos(raw: dict, prefixo: str = "") -> set[str]:
    """Nomes de campo (um nível de aninhamento) — é o que se calibra."""
    encontrados: set[str] = set()
    for chave, valor in (raw or {}).items():
        if isinstance(valor, dict):
            encontrados |= _campos(valor, f"{prefixo}{chave}.")
        else:
            encontrados.add(f"{prefixo}{chave}")
    return encontrados


def _resumir(valor: Any, limite: int = 160) -> Any:
    if isinstance(valor, dict):
        return {k: _resumir(v, limite) for k, v in list(valor.items())[:25]}
    if isinstance(valor, list):
        return [_resumir(v, limite) for v in valor[:3]]
    texto = str(valor)
    return texto if len(texto) <= limite else texto[:limite] + "…"


def _imprimir(linha: dict[str, Any]) -> None:
    marca = {"ok": "✓", "vazio": "○", "timeout": "⏱", "erro": "✗"}.get(linha["status"], "?")
    saude = "saudável" if linha.get("health_check") else "sem resposta"
    print(f"\n{marca} {linha['fonte']}  ({linha['segundos']}s · health_check: {saude})")
    if linha["status"] == "ok":
        print(f"   registros: {linha['registros']}  ·  endpoint: {linha.get('endpoint')}")
        print(f"   id_externo da amostra: {linha.get('id_externo')}")
        campos = linha.get("campos") or []
        listados = ", ".join(campos[:18])
        print(f"   campos ({len(campos)}): {listados}{'…' if len(campos) > 18 else ''}")
    elif linha["status"] == "vazio":
        print("   respondeu, mas sem registros para este município/período")
    else:
        print(f"   {linha.get('erro')}")
    if linha.get("health_erro") and linha["status"] != "erro":
        print(f"   (health_check: {linha['health_erro']})")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Testa as fontes habilitadas ao vivo.")
    parser.add_argument("ibge", help="código IBGE do município (7 dígitos)")
    parser.add_argument("--fonte", action="append", help="limita a fonte(s) (repetível)")
    parser.add_argument("--dias", type=int, default=DIAS_PADRAO, help="janela de coleta")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_PADRAO, help="s por fonte")
    parser.add_argument("--json", action="store_true", help="imprime JSON puro")
    args = parser.parse_args()

    alvos = args.fonte or list(fontes_service.HABILITADAS)
    since = date.today() - timedelta(days=args.dias)

    if not args.json:
        print(f"Probe de {len(alvos)} fonte(s) · município {args.ibge} · desde {since}")

    # sequencial de propósito: fonte de governo costuma limitar concorrência, e
    # o relatório fica legível na ordem em que as fontes respondem
    linhas = []
    for fonte in alvos:
        linha = await _probe(fonte, args.ibge, since, args.timeout)
        linhas.append(linha)
        if not args.json:
            _imprimir(linha)

    if args.json:
        print(json.dumps(linhas, ensure_ascii=False, indent=2, default=str))
    else:
        ok = sum(1 for r in linhas if r["status"] == "ok")
        vazio = sum(1 for r in linhas if r["status"] == "vazio")
        ruim = len(linhas) - ok - vazio
        print(f"\n— {ok} com dados · {vazio} vazias · {ruim} com falha —")

    return 1 if any(r["status"] in ("erro", "timeout") for r in linhas) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
