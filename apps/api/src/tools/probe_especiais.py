"""Probe do módulo `especiais` — o que a API pública realmente expõe.

Existe pelo mesmo motivo do `probe_fontes`: calibrar connector contra fonte de
governo é trabalho empírico. A diferença é o eixo — aqui não se consulta por
município, e sim pelas chaves da PROPOSTA (id do plano de ação, nº da proposta,
id do plano de trabalho), que é como a fonte publica emenda, parlamentar autor e
análise.

Roda sem banco e sem a API no ar: usa o spec do próprio módulo e os connectors.

    cd apps/api
    uv run python -m src.tools.probe_especiais --rotas
    uv run python -m src.tools.probe_especiais --rotas --palavra parlamentar
    uv run python -m src.tools.probe_especiais --id-plano-acao 123456
    uv run python -m src.tools.probe_especiais --numero-proposta 14275/2026 --json

`--rotas` é o primeiro passo de toda calibração: lista as rotas do módulo que
falam do assunto e QUAIS parâmetros cada uma aceita — é daí que sai o valor de
`emendas_esp_endpoint` / `emendas_esp_chave` no painel admin.

Sai com código 1 quando nada respondeu — dá para usar em verificação de deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ..connectors import _especiais
from ..connectors.emendas_especiais import (
    BASE_PADRAO,
    CHAVES,
    PALAVRAS_ROTA,
    EmendaEspecialConnector,
)
from ..ingestion.normalizer_emenda import normalize_emenda

# assuntos que interessam ao enriquecimento da proposta
PALAVRAS_PADRAO = ("emenda", "parlamentar", "analise", "parecer", "historico", "plano_acao")


async def _listar_rotas(base: str, palavras: tuple[str, ...]) -> dict[str, Any]:
    spec = await _especiais.carregar_spec(base)
    if not spec:
        return {"base": base, "status": "erro", "erro": "não baixei o spec do módulo"}

    rotas = _especiais.rotas_do_spec(spec)
    casadas = {
        endpoint: sorted(params)
        for endpoint, params in sorted(rotas.items())
        if any(p in _especiais._norm(endpoint) for p in palavras)
    }
    escolhida = _especiais.escolher_rota(spec, PALAVRAS_ROTA, CHAVES)
    return {
        "base": base,
        "status": "ok",
        "dialeto": "postgrest" if _especiais._e_postgrest(spec) else "openapi3",
        "total_rotas": len(rotas),
        "rotas_do_assunto": casadas,
        "rota_escolhida_para_emenda": (
            {
                "endpoint": escolhida.endpoint,
                "chave": escolhida.chave,
                "paginacao": escolhida.paginacao(1, 50),
            }
            if escolhida
            else None
        ),
    }


async def _coletar(chaves: dict[str, str]) -> dict[str, Any]:
    connector = EmendaEspecialConnector()
    resultado: dict[str, Any] = {"chaves": chaves}
    try:
        rota = await connector.rota()
        resultado["rota"] = (
            {"endpoint": rota.endpoint, "chave": rota.chave} if rota else None
        )
        brutos = await connector.collect_por_proposta(chaves)
    except Exception as exc:  # noqa: BLE001 — o probe RELATA a falha, não morre
        return {**resultado, "status": "erro", "erro": f"{type(exc).__name__}: {exc}"}

    resultado["status"] = "ok"
    resultado["registros"] = len(brutos)
    if brutos:
        # os CAMPOS são o que se calibra — mostrar o primeiro registro inteiro
        resultado["campos"] = sorted(brutos[0])
        resultado["amostra"] = brutos[0]
        canonica = normalize_emenda(brutos[0], fonte="transferegov_emenda")
        resultado["normalizado"] = {
            k: str(v)
            for k, v in canonica.model_dump().items()
            if v is not None and k not in ("detalhe", "proveniencia")
        }
    return resultado


def _imprimir(dados: dict[str, Any]) -> None:
    if dados.get("status") == "erro":
        print(f"  ✗ {dados.get('erro')}")
        return
    for chave, valor in dados.items():
        if chave in ("status", "amostra"):
            continue
        if isinstance(valor, dict):
            print(f"  {chave}:")
            for k, v in valor.items():
                print(f"    · {k}: {v}")
        else:
            print(f"  {chave}: {valor}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe do módulo especiais (TransfereGov)")
    parser.add_argument("--base", default=None, help=f"base URL (default: {BASE_PADRAO})")
    parser.add_argument("--rotas", action="store_true", help="listar rotas do módulo")
    parser.add_argument(
        "--palavra",
        action="append",
        default=None,
        help="assunto a procurar no nome da rota (repita para vários)",
    )
    parser.add_argument("--id-plano-acao", default=None)
    parser.add_argument("--numero-proposta", default=None)
    parser.add_argument("--id-plano-trabalho", default=None)
    parser.add_argument("--json", action="store_true", help="saída JSON")
    args = parser.parse_args()

    base = args.base or BASE_PADRAO
    saida: dict[str, Any] = {}

    if args.rotas or not (args.id_plano_acao or args.numero_proposta or args.id_plano_trabalho):
        palavras = tuple(args.palavra or PALAVRAS_PADRAO)
        saida["rotas"] = await _listar_rotas(base, palavras)

    chaves = {
        k: v
        for k, v in {
            "id_plano_acao": args.id_plano_acao,
            "numero_plano_acao": args.id_plano_acao,
            "numero_proposta": args.numero_proposta,
            "id_plano_trabalho": args.id_plano_trabalho,
            "numero_plano_trabalho": args.id_plano_trabalho,
        }.items()
        if v
    }
    if chaves:
        saida["emendas"] = await _coletar(chaves)

    if args.json:
        print(json.dumps(saida, indent=2, ensure_ascii=False, default=str))
    else:
        for secao, dados in saida.items():
            print(f"\n── {secao} ───────────────────────────────")
            _imprimir(dados)

    return 0 if all(d.get("status") == "ok" for d in saida.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
