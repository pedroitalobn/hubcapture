"""Calibração da Consulta de Programas do TransfereGov (§64).

Roda a consulta REAL (precisa de saída para gov.br — o sandbox de CI/agente
não alcança) e mostra o que o connector enxerga, sem gravar nada:

    python -m src.tools.probe_programas --formulario   # campos, rótulos e opções
    python -m src.tools.probe_programas [--ano 2026]   # filtros aplicados + programas
    python -m src.tools.probe_programas --json

Se um filtro sair `ok: false`, o `--formulario` mostra o texto que a página
usa naquele campo — é ele que entra em `filtros_padrao()`. Sai com código 1
quando a consulta falha ou um filtro não casa.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ..connectors.programas_webapp import Coleta, ProgramasWebappConnector


async def _amain(args: argparse.Namespace) -> int:
    conn = ProgramasWebappConnector()
    if args.formulario:
        inv = await conn.coletar(inventario=True)
        print(json.dumps(inv, ensure_ascii=False, indent=2, default=str))
        return 0
    coleta = await conn.coletar(args.ano, max_paginas=args.paginas, max_detalhes=args.detalhes)
    assert isinstance(coleta, Coleta)
    if args.json:
        print(json.dumps(coleta.__dict__, ensure_ascii=False, indent=2, default=str))
    else:
        print("filtros:")
        for f in coleta.filtros:
            marca = "OK " if f.get("ok") else "FALHOU"
            print(f"  {marca} {f['chave']}: {f.get('opcao')} ({f.get('nome')})")
        print(f"páginas: {coleta.paginas} · fichas visitadas: {coleta.detalhes}")
        print(f"programas: {len(coleta.programas)}")
        for p in coleta.programas[:15]:
            print(
                f"  [{p.get('codigo') or '-'}] id={p.get('id_programa') or '-'} "
                f"{(p.get('nome') or '')[:70]} · fim={p.get('fim_proposta')} "
                f"ufs={','.join(p.get('ufs') or []) or '-'}"
            )
    return 0 if coleta.programas and all(f.get("ok") for f in coleta.filtros) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--formulario", action="store_true", help="só o inventário do formulário")
    ap.add_argument("--ano", type=int, default=None)
    ap.add_argument("--paginas", type=int, default=3)
    ap.add_argument("--detalhes", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    sys.exit(asyncio.run(_amain(ap.parse_args())))


if __name__ == "__main__":
    main()
