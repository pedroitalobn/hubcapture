#!/bin/bash
# Roda UMA vez na primeira inicialização do volume do Postgres.
# Cria a role de aplicação NÃO-superuser: é ela que a API usa em runtime,
# para que o Row-Level Security (RLS) realmente valha.
#   - superuser/BYPASSRLS ignoram policies silenciosamente => segurança falsa.
#   - o owner (POSTGRES_USER) é usado só para migrations (Alembic).
set -euo pipefail

APP_PASSWORD="${APP_DB_PASSWORD:-app_secret}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	DO \$\$
	BEGIN
	  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hubcapture_app') THEN
	    CREATE ROLE hubcapture_app LOGIN PASSWORD '${APP_PASSWORD}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
	  END IF;
	END
	\$\$;

	-- pgvector é extensão não-trusted (exige superuser p/ criar). Criamos aqui,
	-- como o superuser do container, ANTES das migrations. A migration mantém um
	-- CREATE EXTENSION IF NOT EXISTS (no-op idempotente) por portabilidade.
	CREATE EXTENSION IF NOT EXISTS vector;

	GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO hubcapture_app;
	GRANT USAGE ON SCHEMA public TO hubcapture_app;

	-- Privilégios sobre tabelas/sequences que o OWNER criar depois (migrations).
	-- A migration 0002 também concede explicitamente; isto é cinto-e-suspensório.
	ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public
	  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hubcapture_app;
	ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public
	  GRANT USAGE, SELECT ON SEQUENCES TO hubcapture_app;
SQL

echo "[init] role hubcapture_app pronta (NOSUPERUSER NOBYPASSRLS)"
