# Hub Capture

Concentrador de propostas, editais e repasses do governo brasileiro (TransfereGov,
FNS, FNDE, SERPRO). O gestor público consulta, recebe curado por IA, organiza e
monitora tudo num painel — com alertas no WhatsApp em fases futuras.

Monorepo (Turborepo + pnpm). A **API v1 em FastAPI** é a única porta de dados
(web e mobile consomem o mesmo contrato). Ver `CLAUDE.md` (blueprint da stack) e
`docs/ARQUITETURA_HUB_CAPTURE.md` (arquitetura detalhada).

## O que já existe (Sprint 0 + 1)

- **Fundação**: monorepo, `apps/api` (FastAPI + SQLAlchemy 2 async + Alembic),
  `apps/web` (Next 15), `packages/api-client` (client tipado do OpenAPI).
- **Banco**: Postgres 16 + pgvector via docker-compose. Migrations com todas as
  tabelas do schema canônico.
- **RLS por usuário**: isolamento multi-tenant no banco (a API conecta como role
  não-superuser; tenant setado por request via `set_config`).
- **Auth**: fastapi-users (JWT access + refresh), `/auth/register|login|refresh`, `/me`.
- **Ingestão**: connector `transferegov_ff` (PostgREST + retry/backoff),
  normalização → schema canônico + hash + proveniência, scaffold de merge.
- **Cache-first**: `GET /propostas` (lê o cache, RLS filtra) e
  `POST /consulta-avulsa` (fetch on-demand no cache miss/stale).
- **Web**: login + painel listando propostas via client tipado.
- **Testes**: normalização/hash, merge, cache-first e RLS (pytest).

## Como rodar (dev)

```bash
# 1. infra local (Postgres + pgvector; redis/n8n declarados p/ fases seguintes)
cp .env.example .env
docker compose up -d postgres

# ...ou o stack completo (api + web + postgres):  docker compose up -d --build

# 2. API
cd apps/api
uv sync
DATABASE_URL="$DATABASE_MIGRATOR_URL" uv run alembic upgrade head   # roda como owner
uv run uvicorn src.main:app --reload      # http://localhost:8000/api/v1/docs

# 3. Client tipado + web
pnpm install
pnpm --filter @hub/api-client gen:spec     # exporta openapi.json (offline)
pnpm --filter @hub/api-client generate     # gera os tipos TS
pnpm --filter @hub/web dev                 # http://localhost:3000

# testes da API
cd apps/api && uv run pytest
```

> **Nota (banco):** a API usa a role de app `hubcapture_app` (não-superuser) para o
> RLS valer; as migrations rodam como o owner (`DATABASE_MIGRATOR_URL`). Nunca use a
> URL do migrator no runtime.

## Roadmap

Sprints seguintes: onboarding conversacional, favoritos/pastas/monitoramento,
resumo por IA, demais connectors (FNS/FNDE/Discricionárias-CSV/SERPRO), Copiloto e
chat (LangGraph+RAG), WhatsApp (Uniq) e app mobile (Expo). Detalhes no `CLAUDE.md`.
