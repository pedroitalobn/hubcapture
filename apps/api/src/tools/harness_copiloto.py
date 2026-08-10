"""Harness do Copiloto — valida o tool calling SEM banco e SEM rede.

Uso:
    python -m src.tools.harness_copiloto            # validação completa
    python -m src.tools.harness_copiloto --json     # saída em JSON

Roda três baterias com as bordas fake de ai/harness.py (mesmo loop de
produção): (1) estrutura do catálogo TOOLS; (2) tabela de ouro do roteador de
fallback; (3) cenários simulados do loop LLM (multi-rodada, ferramenta
desconhecida, rodadas esgotadas com streaming). Sai com código 1 se algo
falhar — é o probe_fontes do agente."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ..ai import agent, harness


async def _cenarios() -> list[str]:
    erros: list[str] = []

    # 1) multi-rodada: duas ferramentas em rodadas distintas, depois resposta
    eventos = await harness.simular(
        "o que mudou nas minhas propostas?",
        roteiro=[
            harness.Turno(tool_calls=[("minhas_propostas", {})]),
            harness.Turno(tool_calls=[("alertas_atualizacoes", {"apenas_nao_lidos": True})]),
            harness.Turno(conteudo="Você acompanha 2 propostas; 1 alerta novo."),
        ],
        dados={
            "minhas_propostas": {"total": 2, "propostas": []},
            "alertas_atualizacoes": {"total": 1, "alertas": []},
        },
    )
    tools = [e["tool"] for e in eventos if "tool" in e]
    texto = "".join(e.get("delta", "") for e in eventos)
    if tools != ["minhas_propostas", "alertas_atualizacoes"]:
        erros.append(f"multi-rodada: ordem de tools inesperada {tools}")
    if "acompanha 2" not in texto:
        erros.append(f"multi-rodada: resposta final não chegou ({texto!r})")

    # 2) ferramenta desconhecida vira {'erro': ...} e o loop segue
    eventos = await harness.simular(
        "qualquer coisa",
        roteiro=[
            harness.Turno(tool_calls=[("nao_existe", {})]),
            harness.Turno(conteudo="ok"),
        ],
    )
    if "".join(e.get("delta", "") for e in eventos) != "ok":
        erros.append("ferramenta desconhecida derrubou o loop")

    # 3) rodadas esgotadas → resposta final em streaming real
    roteiro = [
        harness.Turno(tool_calls=[("noticias_transferegov", {})]) for _ in range(agent.MAX_RODADAS)
    ]
    roteiro.append(harness.Turno(conteudo="resposta final em stream"))
    eventos = await harness.simular(
        "notícias em loop", roteiro=roteiro, dados={"noticias_transferegov": {"noticias": []}}
    )
    texto = "".join(e.get("delta", "") for e in eventos)
    deltas = [e for e in eventos if "delta" in e]
    if texto != "resposta final em stream":
        erros.append(f"rodadas esgotadas: texto final errado ({texto!r})")
    if len(deltas) < 2:
        erros.append("rodadas esgotadas: resposta não veio em stream (1 delta só)")

    # 4) caminho sem LLM (fallback) formata a resposta da ferramenta
    eventos = await harness.simular(
        "quais propostas vencem este mês?",
        dados={"propostas_prazos": {"janela_dias": 30, "vencendo": []}},
    )
    texto = "".join(e.get("delta", "") for e in eventos)
    if "30 dias" not in texto:
        erros.append(f"fallback: formatação de prazos não veio ({texto!r})")

    return erros


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    args = parser.parse_args()

    estrutura = harness.validar_tools()
    roteamento = harness.validar_roteamento()
    cenarios = asyncio.run(_cenarios())

    resultado = {
        "tools": len(agent.TOOLS),
        "estrutura": estrutura,
        "roteamento": roteamento,
        "cenarios": cenarios,
        "ok": not (estrutura or roteamento or cenarios),
    }
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print(f"catálogo: {resultado['tools']} ferramentas")
        for grupo, erros in (
            ("estrutura", estrutura),
            ("roteamento", roteamento),
            ("cenários", cenarios),
        ):
            if erros:
                print(f"✗ {grupo}:")
                for e in erros:
                    print(f"  - {e}")
            else:
                print(f"✓ {grupo} ok")
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
