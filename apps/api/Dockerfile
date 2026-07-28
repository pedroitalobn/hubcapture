# API FastAPI — Hub Capture
# Build a partir da raiz do monorepo:  docker build -f apps/api/Dockerfile .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

# uv (gerenciador de deps)
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app/apps/api

# camada de deps (cacheável): só o manifesto primeiro
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --no-install-project --no-dev || uv sync --no-dev

# código
COPY apps/api/ ./
RUN uv sync --no-dev

# O ambiente já está pronto e com bytecode compilado (UV_COMPILE_BYTECODE=1).
# Colocar o .venv no PATH deixa o entrypoint chamar `alembic`/`uvicorn` direto,
# sem `uv run` — que a cada execução re-sincroniza o ambiente, reinstala as
# dev-deps (ruff/black/pygments, excluídas por --no-dev) e recompila 6005
# arquivos de bytecode. Isso custava ~11s em TODO start do container e abria
# uma janela de 502 no redeploy (Traefik encaminhando pra porta ainda morta).
# UV_NO_SYNC é o cinto de segurança caso algum `uv run` sobre em outro script.
ENV PATH="/app/apps/api/.venv/bin:${PATH}" \
    UV_NO_SYNC=1

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
