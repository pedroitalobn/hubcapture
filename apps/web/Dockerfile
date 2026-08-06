# Web Next.js — Hub Capture
# Build a partir da raiz do monorepo:  docker build -f apps/web/Dockerfile .
FROM node:20-alpine AS builder
RUN corepack enable
WORKDIR /repo

# NEXT_PUBLIC_* é embutido no bundle no build. Vazio (default) = same-origin:
# o navegador chama /api/v1/* no domínio da web e o rewrite do next.config.mjs
# repassa para a API pela rede interna. Só defina se a API tiver domínio público.
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
# destino interno do rewrite (congelado no build pelo standalone) — no compose
# o host da API é "api"; sobrescreva se a web rodar fora do compose.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}

# manifestos primeiro (camada de deps cacheável) — inclui packages/config,
# que fornece @hub/config/tsconfig.base.json herdado pelo tsconfig da web.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* ./
COPY packages/api-client/package.json packages/api-client/
COPY packages/config/package.json packages/config/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile || pnpm install

# código e build (api-client + config são workspace:*, resolvidos pelo pnpm)
COPY packages/api-client/ packages/api-client/
COPY packages/config/ packages/config/
COPY apps/web/ apps/web/
RUN pnpm --filter web build

# imagem final enxuta (Next standalone)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Bind em 0.0.0.0. O server.js do Next standalone faz
# `const hostname = process.env.HOSTNAME || '0.0.0.0'`, e o Docker injeta
# HOSTNAME com o ID do container em TODO container — então, sem esta linha, o
# Next escuta só no IP do container e recusa conexão em localhost.
#
# Isso derrubava o site a cada deploy: o healthcheck do compose bate em
# http://localhost:3000/, falhava sempre (ECONNREFUSED), o container virava
# unhealthy e o Traefik removia o router do app.hubcapture.com.br — 404, mesmo
# com o app rodando e respondendo 200 pelo IP do container.
#
# Precisa ficar AQUI e não no .env do Dokploy: o .env do compose só interpola
# ${VAR}; sem um bloco `environment:` no serviço, a variável não chega ao
# processo. Definido no Dockerfile, o valor vale pra imagem e vence a injeção
# automática do Docker.
ENV HOSTNAME=0.0.0.0
COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /repo/apps/web/public ./apps/web/public
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
