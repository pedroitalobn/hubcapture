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

# Migrations no boot: LIGADAS por padrão, para todo deploy subir com o schema
# em dia sem passo manual. `AUTOMIGRATE=false` desliga — serve para quem aplica
# a migration por fora (janela controlada, DBA, ou mais de uma réplica da API
# subindo ao mesmo tempo, caso em que dois `alembic upgrade` concorrentes
# disputariam a mesma tabela de versão).
: "${AUTOMIGRATE:=true}"
case "$(printf '%s' "${AUTOMIGRATE}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on) automigrate=1 ;;
  *) automigrate=0 ;;
esac

# `alembic` e `uvicorn` vêm do .venv já montado na imagem (está no PATH). Não
# use `uv run` aqui: ele re-sincroniza o ambiente a cada boot, reinstala as
# dev-deps e recompila o bytecode — ~11s por start, com 502 na janela.
if [ "${automigrate}" = "1" ]; then
  echo "[entrypoint] AUTOMIGRATE=${AUTOMIGRATE} → aplicando migrations (alembic upgrade head)…"
  alembic upgrade head
else
  # Dizer o que NÃO foi feito: sem isto, um schema desatualizado aparece como
  # erro de consulta lá na frente, longe da causa.
  echo "[entrypoint] AUTOMIGRATE=${AUTOMIGRATE} → migrations PULADAS."
  echo "[entrypoint] o schema precisa estar em dia: rode 'alembic upgrade head' por fora."
fi

echo "[entrypoint] subindo API (uvicorn)…"
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
