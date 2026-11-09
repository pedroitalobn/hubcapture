"""Atualiza a malha municipal interna (`src/data/municipios_ibge.csv`) a partir do IBGE.

A busca de municípios (onboarding e "adicionar município" de Minha conta) lê
só o arquivo do repositório — não depende do gov.br em runtime. Quando o IBGE
criar ou renomear um município, roda-se isto numa máquina com acesso ao IBGE
e commita-se o arquivo:

    cd apps/api
    uv run python -m src.tools.atualizar_municipios          # grava o arquivo
    uv run python -m src.tools.atualizar_municipios --check  # só compara

Sai com código 1 se o IBGE não responder ou devolver uma malha suspeita
(menos de 5.500 municípios) — o arquivo atual fica intocado.

A API do IBGE só fornece código, nome e UF. O código SIAFI e as coordenadas da
sede são PRESERVADOS do arquivo atual; município novo entra com essas colunas
vazias e é listado no fim, para completar à mão (SIAFI: Tesouro Nacional;
coordenadas: IBGE, malha de sedes municipais).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from ..core.config import settings
from ..services.municipios import ARQUIVO_MALHA, COLUNAS_MALHA, ler_malha

_MINIMO_PLAUSIVEL = 5500


async def baixar() -> list[tuple[str, str, str]]:
    async with httpx.AsyncClient(
        base_url=settings.ibge_localidades_url, timeout=httpx.Timeout(60.0, connect=15.0)
    ) as client:
        resp = await client.get("municipios", params={"view": "nivelado"})
        resp.raise_for_status()
        linhas = resp.json()
    malha = {
        str(r.get("municipio-id") or ""): (
            str(r.get("municipio-nome") or "").strip(),
            str(r.get("UF-sigla") or "").strip(),
        )
        for r in linhas
    }
    return sorted(
        (ibge, nome, uf) for ibge, (nome, uf) in malha.items() if len(ibge) == 7 and nome and uf
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="só compara, não grava")
    args = parser.parse_args()

    try:
        nova = asyncio.run(baixar())
    except Exception as exc:  # noqa: BLE001
        print(f"IBGE indisponível: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if len(nova) < _MINIMO_PLAUSIVEL:
        print(f"malha suspeita: só {len(nova)} municípios — nada gravado", file=sys.stderr)
        return 1

    malha_atual = ler_malha(ARQUIVO_MALHA)
    atual = {(m["ibge"], m["nome"], m["uf"]) for m in malha_atual}
    extras = {m["ibge"]: m for m in malha_atual}
    entram = sorted(set(nova) - atual)
    saem = sorted(atual - set(nova))
    print(f"IBGE: {len(nova)} municípios · arquivo: {len(atual)}")
    for linha in entram:
        print("  +", ";".join(linha))
    for linha in saem:
        print("  -", ";".join(linha))
    if args.check or not (entram or saem):
        print("nada a gravar" if not (entram or saem) else "(--check: nada gravado)")
        return 0

    sem_extras: list[str] = []
    with ARQUIVO_MALHA.open("w", encoding="utf-8") as f:
        f.write(";".join(COLUNAS_MALHA) + "\n")
        for ibge, nome, uf in nova:
            antigo = extras.get(ibge) or {}
            siafi = antigo.get("siafi") or ""
            lat, lon = antigo.get("latitude"), antigo.get("longitude")
            if not siafi or lat is None or lon is None:
                sem_extras.append(f"{ibge};{nome};{uf}")
            coord = "" if lat is None else f"{lat:.5f}", "" if lon is None else f"{lon:.5f}"
            f.write(f"{ibge};{nome};{uf};{siafi};{coord[0]};{coord[1]}\n")
    print(f"gravado: {ARQUIVO_MALHA}")
    for linha in sem_extras:
        print("  ! sem SIAFI/coordenadas — completar à mão:", linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
