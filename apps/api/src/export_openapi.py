"""Exporta o OpenAPI da API para um arquivo JSON, SEM subir servidor HTTP.

Usado para gerar `packages/api-client/openapi.json` de forma offline e
determinística (o build do client tipado nunca depende da API estar no ar).

    uv run python -m src.export_openapi [caminho_saida]
"""

from __future__ import annotations

import json
import sys

from .main import app


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    spec = app.openapi()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"OpenAPI escrito em {out} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
