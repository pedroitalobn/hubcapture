#!/usr/bin/env bash
# Entrypoint da API no container: espera o Postgres, roda as migrations (como
# owner) e sobe o uvicorn. O bootstrap do superadmin (ADMIN_EMAIL/ADMIN_PASSWORD)
# roda no startup do app (lifespan), depois que o schema já existe.
set -euo pipefail

# espera o Postgres aceitar conexões (host/porta do compose)
: "${DB_HOST:=postgres}"
: "${DB_PORT:=5432}"
echo "[entrypoint] aguardando Postgres em ${DB_HOST}:${DB_PORT}…"
for _ in $(seq 1 60); do
  if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# `alembic` e `uvicorn` vêm do .venv já montado na imagem (está no PATH). Não
# use `uv run` aqui: ele re-sincroniza o ambiente a cada boot, reinstala as
# dev-deps e recompila o bytecode — ~11s por start, com 502 na janela.
echo "[entrypoint] aplicando migrations (alembic upgrade head)…"
alembic upgrade head

echo "[entrypoint] subindo API (uvicorn)…"
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
