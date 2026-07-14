# Web Next.js — Hub Capture
# Build a partir da raiz do monorepo:  docker build -f apps/web/Dockerfile .
FROM node:20-alpine AS builder
RUN corepack enable
WORKDIR /repo

# NEXT_PUBLIC_* é embutido no bundle no build → precisa existir aqui.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# manifestos primeiro (camada de deps cacheável)
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* ./
COPY packages/api-client/package.json packages/api-client/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile || pnpm install

# código e build (o api-client é workspace:*, transpilado pelo Next)
COPY packages/api-client/ packages/api-client/
COPY apps/web/ apps/web/
RUN pnpm --filter web build

# imagem final enxuta (Next standalone)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /repo/apps/web/public ./apps/web/public
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
