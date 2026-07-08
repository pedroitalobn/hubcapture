# CLAUDE.md — Hub Capture

> Blueprint de execução para o Claude Code. Este arquivo é a fonte de verdade da stack, arquitetura, banco e convenções.
> Leia por completo antes de gerar qualquer código. Não invente stack fora daqui; se algo não estiver definido, pergunte.

---

## 0. O que é o Hub Capture

Concentrador de propostas, editais e repasses de recursos das plataformas do governo brasileiro (TransfereGov, FNS, FNDE, SERPRO). O gestor público (parlamentar, prefeitura ou equipe) consulta, recebe curado por IA, organiza e monitora tudo num só painel — com alertas no WhatsApp.

**Decisões travadas (não reabrir sem avisar):**
- API-first: uma **API pública v1 em FastAPI** serve web e mobile (mesmo contrato).
- **Multi-tenancy por usuário individual** (assinatura pessoal). RLS por `usuario_id`.
- **Dois modos de consulta**: agendado (cron, municípios monitorados) + avulso (on-demand, cache-first).
- **Coleta combinada**: API + scraping rodam juntos e fazem *merge* (scraping vence em campos descritivos; API vence em IDs/valores/datas).
- Banco: **Postgres (Neon)** + pgvector. Auth: **JWT no FastAPI (fastapi-users)**.

---

## 1. Stack (versões-alvo — não desviar)

| Camada | Tecnologia | Notas |
|---|---|---|
| Monorepo | **Turborepo 2.x** + pnpm | web + mobile + packages compartilhados |
| API + IA + ingestão | **FastAPI (Python 3.12)** | única porta de dados; OpenAPI; JWT |
| Orquestração agentes | **LangGraph** + **LiteLLM** | Copiloto, resumo, chat com propostas |
| Scraping | **Crawl4AI** (+ Firecrawl opcional) | enriquecimento e fallback |
| Web (site + BFF fino) | **Next.js 15 / React 19** + Tailwind 4 + shadcn/ui | só apresentação; consome API v1 |
| Mobile (fase 2) | **Expo (React Native)** | consome a MESMA API v1 |
| Auth | **fastapi-users** (JWT + refresh) | fonte única de verdade |
| Banco | **Postgres 16 (Neon)** + **pgvector 0.8** | branch por ambiente |
| ORM / migrations | **SQLAlchemy 2** + **Alembic** | tipado, async |
| Validação | **Pydantic v2** | schemas de entrada/saída |
| Jobs/orquestração | **n8n** | cron de sync, detect_changes, alertas, Uniq |
| Fila | **Redis** + **ARQ** | sync pesado, retries, alertas |
| Notificação | **Uniq.chat** (WhatsApp) | alertas + chat IA |
| Deploy | **Dokploy** no VPS (containers) | Docker Compose |
| Client tipado | **openapi-typescript** + **openapi-fetch** | gerado do OpenAPI; web e mobile |

**Proibições:** não usar Prisma/Drizzle (ORM é SQLAlchemy no Python); não colocar lógica de negócio no Next.js; não acessar banco direto pelo Node; não escrever scraper em Node.

---

## 2. Estrutura do monorepo

```
hub-capture/
├── apps/
│   ├── api/                      # FastAPI — API v1 + IA + ingestão
│   │   ├── src/
│   │   │   ├── main.py           # bootstrap FastAPI, monta /api/v1
│   │   │   ├── core/             # config, settings, security (JWT), deps
│   │   │   ├── db/               # engine, session, base SQLAlchemy
│   │   │   ├── models/           # models SQLAlchemy (seção 4)
│   │   │   ├── schemas/          # Pydantic (request/response)
│   │   │   ├── api/v1/           # routers: auth, propostas, favoritos,
│   │   │   │                     #          pastas, monitoramentos, alertas,
│   │   │   │                     #          onboarding, copiloto, consulta_avulsa
│   │   │   ├── connectors/       # um módulo por fonte (seção 5)
│   │   │   │   ├── base.py       # Protocol Connector + registry
│   │   │   │   ├── transferegov_ff.py
│   │   │   │   ├── transferegov_esp.py
│   │   │   │   ├── transferegov_disc.py   # CSV loader
│   │   │   │   ├── fns.py                 # scraping
│   │   │   │   ├── fnde.py                # api + scraping (merge)
│   │   │   │   └── serpro.py              # enrichment
│   │   │   ├── ingestion/        # merge, normalização, dedup, diff, hash
│   │   │   ├── ai/               # LangGraph graphs: resumo, copiloto, chat
│   │   │   ├── jobs/             # tarefas ARQ (sync, embed, alertas)
│   │   │   └── services/         # regras de negócio (cache-first, etc.)
│   │   ├── alembic/              # migrations
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   ├── web/                      # Next.js 15
│   │   ├── app/                  # App Router (rotas, layouts)
│   │   ├── components/           # UI (shadcn)
│   │   ├── lib/api/              # client openapi-fetch (usa @hub/api-client)
│   │   └── Dockerfile
│   └── mobile/                   # Expo (FASE 2 — scaffold só)
├── packages/
│   ├── api-client/               # tipos gerados do OpenAPI (web + mobile)
│   ├── ui/                       # design system compartilhado (opcional)
│   └── config/                   # tsconfig, eslint, tailwind presets
├── infra/
│   ├── docker-compose.yml        # api, web, redis, n8n
│   └── n8n/                      # workflows exportados
├── turbo.json
├── pnpm-workspace.yaml
└── CLAUDE.md
```

---

## 3. Arquitetura em uma imagem

```
Web (Next.js) ─┐
Android (Expo) ─┼─► API v1 (FastAPI, JWT, RLS por usuario_id)
iOS (Expo) ─────┘        │
                         ├─ Motor Hub: normalização · dedup · diff · embeddings
                         ├─ Camada IA: resumo · copiloto · chat (LangGraph+RAG)
                         └─ Ingestão: connectors [API + scraping → merge]
                                 │
                         Postgres/Neon + pgvector  (cache + RLS)
                                 ▲
             n8n ── cron sync D-1 · detect_changes · dispatch_alerts
                        └─► Uniq → WhatsApp (alertas + chat)
```

O Next.js nunca fala com banco nem fonte de governo — chama a API v1 com o JWT do usuário, igual ao mobile.

---

## 4. Arquitetura de banco (Postgres + pgvector)

### Convenções
- IDs internos: `uuid` (default `gen_random_uuid()`), exceto chaves externas de fonte.
- `municipio_ibge` (string, 7 dígitos) é a **chave canônica** de território — todo DE-PARA converge nele.
- Timestamps: `timestamptz`, colunas `created_at` / `updated_at`.
- **RLS ativada** em toda tabela com `usuario_id`; policy compara com `current_setting('app.usuario_id')` setado por request.
- Migrations sempre via Alembic (nunca alterar schema à mão).

### Tabelas

```sql
-- usuários (tenant = usuário individual)
usuarios (
  id            uuid pk,
  nome          text,
  email         text unique,
  senha_hash    text,
  papel         text check (papel in ('parlamentar','executivo','equipe')),
  plano         text,
  telefone_wpp  text,
  optin_wpp     boolean default false,
  created_at    timestamptz default now(),
  updated_at    timestamptz
)

-- municípios que o usuário acompanha (monitorado ou avulso)
municipios_interesse (
  id          uuid pk,
  usuario_id  uuid fk -> usuarios,
  ibge        varchar(7),
  nome        text,
  uf          char(2),
  modo        text check (modo in ('monitorado','avulso')) default 'monitorado',
  created_at  timestamptz default now(),
  unique (usuario_id, ibge)
)

-- preferências capturadas no onboarding
preferencias_usuario (
  usuario_id     uuid pk fk -> usuarios,
  fontes         text[],   -- ['transferegov_ff','fns','fnde',...]
  areas          text[],   -- ['saude','educacao','obras',...]
  monitorar_ativo boolean default true
)

-- PROPOSTA (schema canônico — resultado do merge multi-fonte)
propostas (
  id                    uuid pk,
  fonte                 text,     -- transferegov_ff|_esp|_disc|fns|fnde|serpro
  id_externo            text,     -- NR_CONVENIO / id_programa / id_plano_acao
  numero_proposta       text,
  titulo                text,
  objeto                text,
  orgao_superior        text,
  modalidade            text,
  municipio_ibge        varchar(7),
  municipio_nome        text,
  uf                    char(2),
  valor_total           numeric(15,2),
  contrapartida         numeric(15,2),
  situacao              text,
  emenda                text,
  prazos                jsonb,    -- [{tipo, data_limite}]
  pendencias            jsonb,    -- [{descricao, prazo}]
  movimentacao          text,     -- última movimentação (tipicamente scraping)
  data_atualizacao_fonte date,    -- D-1
  url_origem            text,
  proveniencia          jsonb,    -- {campo: 'api'|'scrape'} — auditoria do merge
  resumo_ia             text,
  hash_conteudo         text,     -- detecção de mudança
  created_at            timestamptz default now(),
  updated_at            timestamptz,
  cache_atualizado_em   timestamptz,   -- TTL do cache-first
  unique (fonte, id_externo)
)

-- embeddings para RAG (pgvector)
proposta_embeddings (
  proposta_id  uuid pk fk -> propostas,
  embedding    vector(1536)   -- ajustar dim ao modelo escolhido
)

-- favoritos
favoritos (
  usuario_id  uuid fk -> usuarios,
  proposta_id uuid fk -> propostas,
  created_at  timestamptz default now(),
  primary key (usuario_id, proposta_id)
)

-- pastas e vínculo
pastas (
  id uuid pk, usuario_id uuid fk -> usuarios,
  nome text, cor text, created_at timestamptz default now()
)
pasta_propostas (
  pasta_id uuid fk -> pastas,
  proposta_id uuid fk -> propostas,
  primary key (pasta_id, proposta_id)
)

-- monitoramento de proposta-chave
monitoramentos (
  id uuid pk,
  usuario_id  uuid fk -> usuarios,
  proposta_id uuid fk -> propostas,
  ativo boolean default true,
  canais text[],   -- ['painel','email','wpp']
  created_at timestamptz default now(),
  unique (usuario_id, proposta_id)
)

-- alertas gerados pela detecção de mudança
alertas (
  id uuid pk,
  usuario_id  uuid fk -> usuarios,
  proposta_id uuid fk -> propostas,
  tipo text,       -- 'status'|'prazo'|'pendencia'
  payload jsonb,   -- antes/depois
  lido boolean default false,
  created_at timestamptz default now()
)

-- execução de sync (agendado e avulso)
sync_runs (
  id uuid pk,
  usuario_id uuid,   -- null p/ sync global
  fonte text,
  tipo text check (tipo in ('agendado','avulso')),
  status text,       -- 'ok'|'degradado'|'erro'
  registros int,
  iniciado_em timestamptz,
  finalizado_em timestamptz,
  erro text
)

-- auditoria
audit_log (
  id uuid pk, usuario_id uuid,
  acao text, entidade text, created_at timestamptz default now()
)
```

### RLS (exemplo de policy)
```sql
ALTER TABLE propostas ENABLE ROW LEVEL SECURITY;
-- usuário só vê propostas dos seus municípios de interesse
CREATE POLICY p_propostas_por_usuario ON propostas
  USING (municipio_ibge IN (
    SELECT ibge FROM municipios_interesse
    WHERE usuario_id = current_setting('app.usuario_id')::uuid
  ));
```
Cada request do FastAPI faz `SET app.usuario_id = <jwt.sub>` na sessão antes de consultar.

---

## 5. Camada de ingestão — connectors

Interface comum:
```python
class Connector(Protocol):
    source_id: str
    def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]: ...
    def health_check(self) -> bool: ...
```

**Coleta combinada (regra central):** para cada fonte com API + URL de consulta, roda os dois e faz merge:
- **API vence**: `id_externo`, `valor_total`, `contrapartida`, datas, `numero_proposta`.
- **Scraping vence (mais atual)**: `situacao`, `pendencias`, `movimentacao`.
- Cada valor registra origem em `proveniencia`.
- Se um lado falha → o outro assume (fallback + degradação graciosa).

Fontes e endpoints reais:
- `transferegov_ff` → `https://api.transferegov.gestao.gov.br/fundoafundo/` (PostgREST: `?campo=eq.valor`). ✅ responde.
- `transferegov_esp` → `.../transferenciasespeciais/`. ⚠️ instável → merge/fallback com scraping obrigatório.
- `transferegov_disc` → **sem API**; CSV diário em `http://repositorio.dados.gov.br/seges/detru/`. Loader agendado.
- `fns` → scraping (Crawl4AI) do portal de consultas. Fonte primária por scraping.
- `fnde` → API + scraping (merge).
- `serpro` → API direta, usada para enrichment/cruzamento.

---

## 6. API v1 — contrato base

```
POST /api/v1/auth/register · /login · /refresh
GET  /api/v1/me
POST /api/v1/onboarding                 # grava municípios/fontes + dispara 1º sync
GET  /api/v1/propostas?municipio=&fonte=&area=&situacao=   # cache-first
GET  /api/v1/propostas/{id}
POST /api/v1/consulta-avulsa            # fetch on-demand (cache miss/stale)
GET/POST/DELETE /api/v1/favoritos
GET/POST/PATCH  /api/v1/pastas
POST /api/v1/monitoramentos
GET  /api/v1/alertas
POST /api/v1/copiloto/chat              # SSE stream (RAG)
GET  /api/v1/openapi.json               # gera client tipado
```
Toda rota autenticada aplica RLS. Respostas tipadas com Pydantic.

---

## 7. Camada de IA (LangGraph)

- **Resumo** — roda no pipeline de ingestão (batch), não no clique. Gera `resumo_ia` adaptado ao papel. Modelo menor (custo).
- **Copiloto** — ensina passos, sugere tutoriais. RAG sobre base de conhecimento própria (docs TransfereGov) em pgvector.
- **Chat com propostas** — RAG sobre as propostas do usuário (com RLS). Serve painel e WhatsApp. Modelo maior.
- LiteLLM roteia os modelos; trocar provider sem mexer no grafo.

---

## 8. Jobs (n8n + ARQ)

| Job | Quando | Ação |
|---|---|---|
| sync por fonte (ff/esp/disc/fns/fnde) | diário D-1 | coleta municípios monitorados → merge → cache |
| enrich_serpro | diário | cruza/enriquece |
| detect_changes | após sync | compara hash → gera alertas |
| dispatch_alerts | contínuo | envia painel/email/Uniq |
| embed_new | após sync | embeddings das novas/alteradas |
| consulta_avulsa | on-demand (API) | fetch ao vivo no cache miss → cacheia |

---

## 9. Ordem de construção (roadmap de execução)

**Sprint 0 — fundação**
1. Turborepo + pnpm + estrutura de pastas (seção 2).
2. `apps/api`: FastAPI + SQLAlchemy + Alembic + conexão Neon.
3. Migrations das tabelas (seção 4) + RLS + pgvector.
4. Auth (fastapi-users): register/login/refresh + JWT + `SET app.usuario_id`.

**Sprint 1 — primeiro vertical ponta a ponta**
5. Connector `transferegov_ff` (o que responde) com merge scaffold.
6. Normalização → schema canônico `propostas` + dedup + hash.
7. Endpoints `propostas` (cache-first) e `consulta-avulsa`.
8. `apps/web`: login + painel listando propostas (client tipado do OpenAPI).

**Sprint 2 — onboarding e curadoria**
9. `POST /onboarding` + wizard no web + 1º sync dirigido.
10. Favoritos, pastas, tabs. Resumo por IA no pipeline.

**Sprint 3 — monitoramento**
11. Monitoramentos + detect_changes + alertas (painel/email).
12. n8n: cron de sync + dispatch_alerts.

**Sprint 4 — demais fontes + IA**
13. Connectors fns/fnde/disc(CSV)/serpro com merge.
14. Copiloto + chat com propostas (LangGraph + RAG).

**Fase 2**
15. WhatsApp via Uniq (alertas + chat). Mobile (Expo) consumindo API v1.

---

## 10. Convenções de código

- **Python**: ruff + black; type hints obrigatórios; async em I/O; Pydantic v2 para schemas.
- **TS**: eslint + prettier; nunca `any`; usar tipos gerados em `@hub/api-client`.
- **Commits**: conventional commits.
- **Segredos**: `.env` (nunca commitar); settings via Pydantic Settings.
- **Testes**: pytest no api (mínimo: connectors, merge, RLS, endpoints).
- **Erros de fonte**: registrar em `sync_runs`, nunca engolir silenciosamente.
- **Cache-first**: toda leitura de proposta passa pelo cache antes de qualquer fetch ao vivo.

---

## 11. Como rodar (dev)

```bash
pnpm install
# api
cd apps/api && uv sync && alembic upgrade head && uvicorn src.main:app --reload
# web
cd apps/web && pnpm dev
# infra (redis, n8n)
docker compose -f infra/docker-compose.yml up -d
```

---

## 12. Quando estiver em dúvida
- Território sempre por `municipio_ibge` (7 dígitos).
- Novo campo de proposta? Adicione ao schema canônico (seção 4) e ao merge (seção 5).
- Nova fonte? Novo connector implementando o Protocol — não reescreva o core.
- Não sabe uma decisão de produto? Pergunte antes de assumir.

---

## 13. Expansão — Recursos recebidos (benchmark Virtù)

> Eixo **complementar** à captação: além de propostas/editais (frente), o Hub passa a cobrir
> **recursos já recebidos** (recebidos), **conformidade fiscal** e **execução/obras**. Ciclo:
> captar → receber → executar → prestar contas. As decisões travadas (seção 0) permanecem.

**Entidades canônicas** (uma por eixo, todas escopadas por `municipio_ibge` + RLS):
`proposta` (captação, seção 4) · **`repasse`** (recebidos — ver abaixo) · `conformidade` (fiscal, roadmap) · `obra` (execução, roadmap).

**Tabela `repasses`** (implementada — cache global, RLS só-SELECT por município, igual a `propostas`):
`id, fonte (fns|fnde|fpm|emendas|transferegov_ff|caixa), id_externo, municipio_ibge/nome/uf,
data_repasse, competencia, descricao, categoria, orgao_superior, natureza (credito|deducao|repasse),
valor, documento, emenda, detalhe jsonb, proveniencia jsonb, hash_conteudo, cache_atualizado_em`.
`unique(fonte, id_externo)`. A `natureza` permite a decomposição crédito/dedução do FPM
(líquido = Σ crédito − Σ dedução no agregado da Visão Geral).

**Connectors novos** (Protocol de `connectors/base.py`, retry via `connectors/_http.py`):
`fpm.py` (decêndios do Tesouro), `emendas.py`. Normalizador próprio em
`ingestion/normalizer_repasse.py` (reusa `compute_hash`). Serviço `services/repasses.py`
(cache-first + `visao_geral` + `sync_municipio`). Endpoints: `GET /repasses`,
`GET /repasses/visao-geral`, `POST /repasses/sync`.

**Catálogo de fontes (connector-first — todas do Virtù + outras):** FNS, FNDE, FPM, Emendas
(recebidos) · Siconfi/CAUC/CAPAG, órgãos de conformidade (fiscal) · SISMOB, SIMEC, CAIXA/SIORB
(obras) · TransfereGov (FF/Esp/Disc), SERPRO (captação) · TSE (eleições, futuro) · IBGE (geodados).
Adicionar fonte = novo módulo connector + mapeamento no normalizador da entidade-alvo; o core não muda.

**Roadmap da expansão:** P1 Recursos recebidos (feito: FPM/Emendas + dashboard) → P2 Conformidade
fiscal (CAUC/CAPAG via CSV do Tesouro) → P3 Obras (SISMOB/SIMEC/CAIXA + mapa Leaflet).

**Design system (web):** `components/` reutilizáveis — `StatCard`, `StatusBadge`, `FilterChips`,
`DateRangePresets`, `Feed` (agrupado por data), `Skeleton`. Página `app/painel/repasses`.
Atenção: **mascarar dados bancários** por `papel` (privacidade).
