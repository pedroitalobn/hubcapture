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

# Scraping local (browser headless). ON por padrão: sem ele o painel da Visão
# Geral do TransfereGov e a consulta do FNS não rendem — as duas páginas só
# existem depois que o JS roda, e sem provider a coleta dessas fontes degrada.
# Custa ~500MB de imagem (Chromium + libs); `--build-arg COM_SCRAPING=0` monta a
# imagem enxuta para quem usa scraper externo (servidor Crawl4AI/Firecrawl).
ARG COM_SCRAPING=1

# camada de deps (cacheável): só o manifesto primeiro
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN if [ "$COM_SCRAPING" = "1" ]; then \
      uv sync --no-install-project --no-dev --extra scraping || uv sync --no-dev --extra scraping; \
    else \
      uv sync --no-install-project --no-dev || uv sync --no-dev; \
    fi

# Chromium + libs do sistema na mesma camada das deps (o browser fica em
# /root/.cache/ms-playwright, que é onde o Playwright procura em runtime).
RUN if [ "$COM_SCRAPING" = "1" ]; then \
      .venv/bin/playwright install --with-deps chromium \
      && rm -rf /var/lib/apt/lists/*; \
    fi

# código
COPY apps/api/ ./
RUN if [ "$COM_SCRAPING" = "1" ]; then uv sync --no-dev --extra scraping; else uv sync --no-dev; fi

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
