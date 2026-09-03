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
- `transferegov_esp` → **API pública** `https://api-publica.transferegov.gestao.gov.br/especiais/` (docs em `<base>/docs`) + fallback scraping.
- `transferegov_voluntarias` → **API pública** `https://api-publica.transferegov.gestao.gov.br/voluntarias/` (convênios/discricionárias on-line) + fallback scraping.
- `transferegov_disc` → CSV diário em `http://repositorio.dados.gov.br/seges/detru/`. Loader agendado.
- `fns` → scraping (facade Crawl4AI/Firecrawl) do portal de consultas. Fonte primária por scraping.
- `fnde` → API + scraping (merge).
- `serpro` → painel público `https://dd-publico.serpro.gov.br/extensions/painel/painel.html` (Qlik, JS pesado → extração via scraping headless) + API gateway (token) p/ enrichment/cruzamento.

---

## 6. API v1 — contrato base

```
POST /api/v1/auth/register · /login · /refresh
GET  /api/v1/me
POST /api/v1/onboarding                 # grava municípios/fontes + dispara 1º sync
GET  /api/v1/proposals?municipio=&fonte=&area=&situacao=   # cache-first
GET  /api/v1/proposals/{id}
POST /api/v1/proposals/live-search            # fetch on-demand (cache miss/stale)
GET/POST/DELETE /api/v1/favorites
GET/POST/PATCH  /api/v1/folders
POST /api/v1/monitors
GET  /api/v1/alerts
POST /api/v1/copilot/chat              # SSE stream (RAG)
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
# stack completo (postgres + api + web; redis incluso, n8n no perfil orchestration)
docker compose up -d --build
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
(cache-first + `visao_geral` + `sync_municipio`). Endpoints: `GET /transfers`,
`GET /transfers/overview`, `POST /transfers/sync`.

**Catálogo de fontes (connector-first — todas do Virtù + outras):** FNS, FNDE, FPM, Emendas
(recebidos) · Siconfi/CAUC/CAPAG, órgãos de conformidade (fiscal) · SISMOB, SIMEC, CAIXA/SIORB
(obras) · TransfereGov (FF/Esp/Disc), SERPRO (captação) · TSE (eleições, futuro) · IBGE (geodados).
Adicionar fonte = novo módulo connector + mapeamento no normalizador da entidade-alvo; o core não muda.

**Roadmap da expansão:** P1 Recursos recebidos (feito: FPM/Emendas + dashboard) → P2 Conformidade
fiscal (CAUC/CAPAG via CSV do Tesouro) → P3 Obras (SISMOB/SIMEC/CAIXA + mapa Leaflet).

**Design system (web):** `components/` reutilizáveis — `StatCard`, `StatusBadge`, `FilterChips`,
`DateRangePresets`, `Feed` (agrupado por data), `Skeleton`. Página `app/panel/transfers`.
Atenção: **mascarar dados bancários** por `papel` (privacidade).

---

## 14. Plataforma — usuários, convites e planos (v1)

Módulo de administração (admin = `is_superuser`). Tabelas **platform-level (sem RLS por-tenant)**:
- `planos` (catálogo: nome, slug, `preco_mensal`, `limites` jsonb, ativo) — atribuído via `usuarios.plano_id`.
- `convites` (email, token, papel, plano, expiração, status) — fluxo de convite.

Endpoints: `GET /plans` (público) · `POST/PATCH /plans` (admin) · `POST /admin/users` ·
`PATCH /admin/users/{id}/plano` · `POST /admin/invites` · `GET /admin/invites` ·
`POST /auth/accept-invite` (público). Criação de usuário passa pelo UserManager
(hash de senha). Dependency `current_superuser` em `core/users.py`.

**Web (painel de administração unificado):** `app/admin/layout.tsx` é o shell com guard de
superuser (`/users/me` → redirect se não-admin) e navegação Usuários · Convites · Planos ·
Providers & Config. Usuários: criar + editar inline papel/plano/admin/ativo
(`PATCH /admin/users/{id}` com `plano_id`). Convites: criar com papel/plano/validade,
listar com status e **copiar link** (`/accept-invite?token=…`). A página pública
`app/accept-invite` consome o token (nome+senha → aceite → login → onboarding). O menu do
painel comum mostra "Administração" só para superusers.

## 15. Ingestão pronta para as APIs + scraping (Crawl4AI + Firecrawl)

Todos os connectors estão **registrados** (`connectors/*`), com rotas/campos isolados em
constantes (ponto de calibração): transferegov_ff/esp/voluntarias/disc(CSV)/fns/fnde/serpro +
fpm/emendas. Retry/backoff compartilhado em `connectors/_http.py`.

**Scraping em facade** (`scraping/scraper.py::get_scraper`): os connectors nunca chamam um
provider direto. Providers: **Crawl4AI** (`scraping/crawl4ai.py`, servidor Docker self-hosted —
`crawl4ai_base_url` + token opcional) e **Firecrawl** (`scraping/firecrawl.py`,
`firecrawl_api_key`). Ordem por `scraping_provider` (`auto` = Crawl4AI primeiro, Firecrawl
fallback); provider sem credencial fica fora da rodada; nenhum configurado →
`ScraperNotConfigured` (registrado em `sync_runs`). O resultado carrega `_scraper` e a
proveniência marca `scrape` nos campos vindos de scraping.

Resumo por IA em `ai/resumo.py` (LiteLLM, import preguiçoso; desabilita sem `LLM_API_KEY`).
Para ativar uma fonte real: preencher a URL/credencial no painel admin (ou `.env`), calibrar
os nomes de campo do connector e (se scraping) o schema de extração.

## 16. Painel admin de configuração (credenciais dos providers via API)

As credenciais/URLs dos providers são geridas em **runtime** pelo admin (não só via `.env`).
Tabela `configuracoes` (platform-level, sem RLS); segredos **cifrados em repouso** (Fernet,
chave de `CONFIG_SECRET_KEY`) e **mascarados** na leitura. Catálogo de chaves em
`services/config.py::CATALOGO` (Firecrawl, LLM, base URLs/tokens das fontes).

- Endpoints (admin `is_superuser`): `GET /admin/config` (lista mascarada) · `PUT /admin/config` (`{chave, valor}`) ·
  `GET /admin/sources` (**diagnóstico**: health_check ao vivo de todos os connectors em paralelo
  com timeout + última coleta por fonte de `sync_runs` + estado de Firecrawl/Crawl4AI/LLM/chave
  de emendas — página `app/admin/sources`). A API de emendas (Portal da Transparência) EXIGE a
  chave `chave-api-dados` (`emendas_api_key`, cadastro gratuito); sem ela o connector falha com
  mensagem clara em `sync_runs`.
- `services/config.resolver(chave)` é a fonte de verdade em runtime (DB decifrado > default `.env`).
  Firecrawl (`scraping/firecrawl.py`), o resumo IA (`ai/resumo.py`) e **todos os connectors**
  (base URL no `collect`) consultam o resolver. Plugar uma credencial no painel ativa o provider
  sem redeploy.
- Web: `app/admin/config` — **menu lateral por categoria** (IA · Scraping · Fontes · WhatsApp ·
  E-mail); cada categoria mostra os provedores **ativos** e um fluxo "Adicionar provedor" para os
  inativos (segredos em campo password, mascarados).
- **LLMs multi-provedor** (`services/llm_providers.py`): registry cobrindo Anthropic, OpenAI,
  Gemini, DeepSeek, Grok (xAI), Kimi (Moonshot), Qwen (Alibaba) e GLM (Z.ai), cada um com sua
  chave (`llm_<id>_api_key`). Ao colar a API key (`PUT /admin/config/llm/{id}/chave`) os modelos
  do provedor são listados **ao vivo** do endpoint `/models` da fonte (fallback curado se falhar)
  — menor fricção. Modelos escolhidos são salvos como `<provider>/<modelo>` em
  `llm_model_chat`/`llm_model_resumo`; `params_para()` resolve p/ LiteLLM (prefixo nativo ou
  rota OpenAI-compatible + `api_base`). Valor sem prefixo conhecido = caminho legado (`llm_api_key`).

## 17. Camada de IA + WhatsApp + PDF (v1)

- **Embeddings/RAG**: `ai/embeddings.py` (LiteLLM), `services/rag.py` (similaridade pgvector
  sob RLS + fallback textual), `jobs/embed.py` (embed_new). Dim 1536.
- **Chat/Copiloto**: `ai/chat.py` (LiteLLM streaming, fallback sem chave). `POST /copilot/chat`
  (SSE) — modo `propostas` (RAG sobre as propostas do usuário) ou `copiloto` (base_conhecimento).
  Web: `app/panel/copilot`.
- **WhatsApp (Uniq)**: `notifications/uniq.py`, `POST /webhooks/uniq` (telefone→usuário→chat→resposta),
  `services/dispatch_alerts.py`. Credenciais no painel (categoria whatsapp).
- **Exportar PDF**: `services/pdf.py` (reportlab), `GET /proposals/{id}/pdf`. Web: botão PDF no painel.
- Todos os providers de IA/WhatsApp são **opcionais** e ligados pelo painel admin (`/admin/config`);
  sem credencial, degradam com elegância (o Hub continua entregando dados).

## 18. Conformidade fiscal (CAUC/CAPAG) — P2

Terceiro eixo do ciclo (fiscal). Entidade `conformidades` (cache global, RLS só-SELECT por
município, migration 0007). Connector `siconfi` (CSV do Tesouro Transparente; base URL no painel
`siconfi_csv_url`), normalizador `ingestion/normalizer_conformidade.py`, serviço
`services/conformidade.py` (listar/upsert/resumo/sync). Endpoints `GET /compliance` (KPIs por
status/seção + CAPAG) e `POST /compliance/sync`. Web `app/panel/compliance`.

## 19. Navegação profile-centric (decisão travada)

O Hub Capture **não** é orientado a fonte de dados. Ao contrário de outras plataformas que
expõem no menu uma aba por fonte (TransfereGov, Fundo Nacional de Saúde, FNDE…), aqui a
navegação **parte do PERFIL do usuário**: o(s) `municipios_interesse`, as `areas` de
`preferencias_usuario` e o `papel`. As fontes são detalhe de ingestão (connectors), nunca a
espinha da UI.

- **Backend** — `services/perfil.py` + `api/v1/perfil.py`:
  `GET /profile` (território: municípios + áreas + papel) e `GET /profile/overview` (agrega as
  **dimensões do ciclo** — captação/recebidos/conformidade/obras — já recortadas pelo território
  via RLS; nenhuma agregação é feita "por fonte"). Schemas em `schemas/perfil.py`.
- **Web** — `app/panel/layout.tsx` é o shell profile-centric: cabeçalho com o **território** e o
  **papel**, e um menu que são **lentes sobre o município do usuário** (Meu painel · Captação ·
  Recursos recebidos · Conformidade · Obras · Copiloto), não abas de plataforma. `app/panel/page.tsx`
  é o **Meu painel** (cards por dimensão vindos de `/profile/overview`). A antiga lista de propostas
  virou `app/panel/funding`. Sem território → CTA para o onboarding (o perfil é o ponto de partida).
- Adicionar fonte continua sendo só um novo connector; **nunca** vira uma aba nova na navegação.

## 19b. Onboarding conversacional + primeiro sync real (decisão travada)

A porta de entrada do app é o **onboarding conversacional**: após login/cadastro sem
território, o usuário cai em `/onboarding`, onde o Copiloto pergunta em chat guiado —
papel → município(s) (busca por nome via IBGE) → áreas de interesse → fontes (pré-marcadas
pelas áreas) → confirmação. Nada de formulário em página; a conversa é o wizard.

- **Busca de municípios** — `services/municipios.py` + `GET /municipalities?q=` (IBGE
  Localidades, cache em memória 24h, chave `ibge_localidades_url` no painel). Degrada
  para lista vazia; o front aceita código IBGE de 7 dígitos digitado direto.
- **Primeiro sync (dados reais)** — ao confirmar, `POST /onboarding` grava o perfil e
  agenda `services/primeiro_sync.executar` cobrindo as 4 dimensões (captação via
  consulta-avulsa, recebidos por fonte, conformidade, obras por área), cada fonte
  best-effort com incidente em `sync_runs`. ATENÇÃO: o agendamento é
  `asyncio.create_task` (`primeiro_sync.agendar`) — **nunca** `BackgroundTasks`, que
  executa antes do teardown/commit da sessão RLS do request e trava o perfil atrás do
  sync (lock em `municipios_interesse`/`usuarios`).
- **Feed de novidades** — `GET /profile/feed` (schemas em `schemas/perfil.py`):
  últimas propostas + repasses do território, recortados pelas fontes do perfil e pelas
  fontes derivadas das áreas (`services/perfil.py::AREA_FONTES`), intercalados por data,
  mais o estado honesto da coleta (última execução por fonte em `sync_runs`). O Meu
  painel (`app/panel/page.tsx`) mostra o feed e, vindo do onboarding (`?sync=1`), faz
  polling ~8s até os primeiros dados chegarem.
- **Login** (`app/login`) → `GET /profile`: sem município → `/onboarding`; com território →
  `/painel`. O cadastro segue direto para o onboarding.

## 20. Obras (execução — SISMOB/SIMEC/CAIXA) — P3

Quarto e último eixo do ciclo (execução), fechando captar → receber → executar → prestar
contas. Entidade `obras` (cache global, RLS só-SELECT por município, migration `66ddf34515bd`):
`fonte (sismob|simec|caixa), id_externo, municipio_ibge/nome/uf, nome, objeto, programa, eixo
(saude|educacao|infraestrutura), situacao (planejada|em_execucao|paralisada|concluida|cancelada),
percentual_execucao, valor_investimento, valor_repassado, data_inicio, data_fim_prevista,
latitude, longitude, endereco, orgao, detalhe/proveniencia jsonb, hash_conteudo`.
`unique(fonte, id_externo)`.

- **Connectors** (Protocol de `connectors/base.py`, JSON via `_http.get_json`, campos isolados em
  constantes p/ calibração; base URL no painel): `sismob.py` (saúde/MS), `simec.py` (educação/FNDE),
  `caixa.py` (infra/OGU+APF). Normalizador `ingestion/normalizer_obra.py` (de-para de situação +
  `compute_hash` sobre andamento). Chaves de config: `sismob_base_url`, `simec_base_url`,
  `caixa_obras_base_url` (categoria fonte).
- **Serviço** `services/obras.py`: `listar` (cache-first, RLS, filtros fonte/situação), `upsert`
  (on_conflict por `(fonte,id_externo)`), `resumo` (KPIs de execução + quebra por situação + obras
  com geo), `sync_municipio` **multi-fonte best-effort** (cada fonte que falha registra `sync_runs`
  e não derruba as demais). Endpoints `GET /works`, `GET /works/summary`, `POST /works/sync`.
- **Perfil**: a dimensão "obras" da `/profile/overview` passa a contar obras reais (antes era
  placeholder "em breve").
- **Web** `app/panel/works`: KPIs, **mini-mapa offline** (dispersa obras por lat/long sem tiles
  externos — em produção pode virar Leaflet+GeoJSON), chips por situação e lista. Mascaramento por
  papel segue a mesma diretriz de privacidade dos demais eixos.

## 21. Essenciais de SaaS — recuperação de senha + e-mail transacional

Fecha os itens de plataforma que todo SaaS precisa além do CRUD do produto.

- **Recuperação de senha / verificação**: routers do fastapi-users montados em
  `api/v1/auth.py` — `POST /auth/forgot-password`, `/auth/reset-password`,
  `/auth/request-verify-token`, `/auth/verify`. Os hooks do `UserManager`
  (`on_after_forgot_password`, `on_after_request_verify`, `on_after_register`)
  disparam e-mail com link para `{app_base_url}/reset-password?token=…` (e
  `/verify-email`).
- **Camada de e-mail** (`notifications/email.py`): SMTP via `smtplib` (stdlib, em
  thread), **provider-opcional** como o Uniq — sem `email_smtp_host`+`email_from`
  no painel, o envio degrada (retorna False, sem erro) e o fluxo de negócio segue
  (o token ainda existe na API). Suporta STARTTLS (587) e SSL (465). Templates
  txt+HTML em `notifications/email_templates.py` (boas-vindas, redefinir senha,
  verificar e-mail, convite).
- **Convite por e-mail**: `services/gestao_usuarios.criar_convite` envia o link de
  aceite (`/accept-invite?token=…`) — best-effort.
- **Config (painel admin, categoria `email`)**: `email_smtp_host`,
  `email_smtp_port`, `email_smtp_user`, `email_smtp_password` (segredo cifrado),
  `email_from`, `app_base_url`. A página `/admin/config` agrupa por categoria
  automaticamente — a categoria `email` aparece sem alteração de UI.
- **Web (telas de auth)**: `app/signup` (self-signup), `app/forgot-password`
  (solicita link), `app/reset-password` (consome o token; usa Suspense p/
  `useSearchParams`), `app/verify-email` (confirma o token), com links no
  `app/login`. Nunca revela se um e-mail existe.
- **Conta do usuário**: router `get_users_router` montado em `/users` →
  `GET/PATCH /users/me` (editar perfil e trocar senha logado; admin em
  `/users/{id}`). Web `app/panel/account` (nome/telefone/opt-in WhatsApp + trocar
  senha), no menu profile-centric.

## 22. Deploy local via Docker Compose + admin inicial

Stack completo sobe com um comando; o superadmin é criado no boot.

- **Compose** (`./docker-compose.yml`, na raiz — composePath de deploy): `postgres`
  (pgvector) · `api` (FastAPI) · `web` (Next standalone) · `redis` · `n8n` (perfil
  `orchestration`). `api` depende do Postgres saudável; dentro da rede o host do banco é
  `postgres` (não `localhost`); o serviço `api` sobrescreve `DATABASE_URL`/
  `DATABASE_MIGRATOR_URL` para apontar a `postgres:5432` e carrega o `.env` via
  `env_file`. Os scripts de init do Postgres seguem em `infra/init/`.
  Subir: `docker compose up -d --build`.
- **Portas / proxy**: o compose de deploy usa `expose` (NÃO publica portas no host)
  — em plataformas com proxy (Dokploy/Traefik) portas fixas colidem. No painel aponte
  o domínio para `web:3000`. A web faz **proxy same-origin** da API: o navegador chama
  `/api/v1/*` no domínio da web e o rewrite do `next.config.mjs` repassa à API pela rede
  interna (`API_INTERNAL_URL`, default `http://api:8000`) — a API não precisa de domínio
  público. Só defina `NEXT_PUBLIC_API_URL` (build arg) se quiser expor a API num domínio
  próprio e o front chamá-la direto. Para dev local,
  `docker-compose.override.yml` publica 3000/8000/5432 e é auto-carregado por
  `docker compose up` (o Dokploy roda com `-f`, ignorando o override).
- **Dockerfiles**: `apps/api/Dockerfile` (uv sync; `docker-entrypoint.sh` espera o
  Postgres → `alembic upgrade head` → uvicorn) e `apps/web/Dockerfile` (build pnpm do
  monorepo → Next standalone). `.dockerignore` na raiz enxuga o contexto.
- **Admin inicial (bootstrap)**: `core/bootstrap.ensure_admin()` roda no `lifespan` da
  API. Com `ADMIN_EMAIL`+`ADMIN_PASSWORD` no `.env`, cria/promove um superusuário
  (idempotente — não duplica nem reseta senha existente). Destrava o 1º login no painel.
  Atenção: `email-validator` rejeita domínios reservados (`.local`) — use domínio válido.
- **Painel admin de usuários** (`app/admin/users`, superuser): cria usuário com
  **papel (role)** + **plano** + **permissão de admin (`is_superuser`)**; lista todos e
  alterna papel/admin/ativo inline. Backend: `GET /admin/users`,
  `POST /admin/users` (agora aceita `is_superuser`), `PATCH /admin/users/{id}`
  (papel/is_superuser/is_active/plano). Env `ADMIN_EMAIL`/`ADMIN_PASSWORD`/`APP_BASE_URL`.

## 23. Jornada completa do fluxograma — gaps fechados (v1)

Fecha os gaps entre o fluxograma de jornada (5 etapas) e o produto:

- **Eixo "QUE TIPO?" (cadastrada × disponível)**: derivado da `situacao` por de-para de
  palavras-chave em `services/proposals.py::classificar_tipo` (sem coluna nova; calibrável).
  Exposto como campo computado `tipo` no `PropostaRead` e filtro `?tipo=` em `GET /proposals`.
- **Filtros de granularidade**: `GET /proposals` aceita `valor_min/valor_max/area/tipo`
  (área → fontes via `AREA_FONTES`). `GET /proposals/deadlines?dias=` responde "o que vence
  na janela" (parse do jsonb `prazos`); o copiloto injeta esse contexto estruturado quando a
  pergunta menciona prazo/vencimento (`api/v1/copiloto.py::_contexto_prazos`).
- **Monitoramento de FUTURAS propostas**: tabela `monitoramentos_busca` (migration
  `b1f2c3d4e5a6`, RLS por-tenant) — vigia município (+área/fonte opcional) com `canais`
  (painel/email/wpp) e cursor `ultimo_alerta_em`. Endpoints
  `GET/POST/DELETE /monitors/searches`. O onboarding cria uma busca por município
  quando `monitorar_ativo`.
- **Varredura + alerta de oportunidade** (`services/oportunidades.py`, endpoint
  `POST /alerts/scan`): (1) `nova_proposta` — propostas que entraram no cache após o
  cursor das buscas ativas; (2) `oportunidade` — o alerta do fluxograma "recursos
  disponíveis com propostas não cadastradas" (repasses da fonte X no município sem nenhuma
  proposta da fonte X; `alertas.proposta_id` agora é nullable; dedupe por alerta não-lido).
  Despacho best-effort por e-mail (template `alertas_resumo`) e WhatsApp (Uniq) conforme canais.
- **Onboarding com passo "ativar avisos"**: `OnboardingRequest` ganhou
  `telefone_wpp/optin_wpp/canais_alerta`; o chat de onboarding pergunta canais e WhatsApp
  antes da confirmação.
- **Enforcement de planos (3 tiers × municípios)**: `limites.municipios_max` do plano é
  validado no onboarding (`LimitePlanoExcedido` → 403 `LIMITE_PLANO_MUNICIPIOS`).
- **Painel informativo**: `services/noticias.py` (RSS gov.br, cache 1h, degrada p/ vazio),
  `GET /news`, chave `transferegov_noticias_url` no painel admin. Widget no Meu painel.
- **SERPRO painel**: default de `serpro_painel_url` aponta para
  `TransferegovbrVisaoGeral.html` (dados ricos via scraping headless; API pública primeiro,
  painel enriquece/faz fallback — coleta combinada da seção 5).
- **Web**: captação com abas locais (várias frentes), chips cadastrada/disponíveis, filtros
  (fonte/área/situação/valor), favoritar ★, pastas (criar/atribuir/filtrar), resumo IA na
  lista; página de detalhe `app/panel/funding/[id]` em seções (dados gerais, valores,
  situação, prazos, pendências, proveniência) com monitorar/PDF; central
  `app/panel/alerts` (varredura, marcar lido, monitorar futuras propostas) no menu;
  card de alertas não lidos + notícias no Meu painel.

## 24. Copiloto em Dynamic Island (tool calling)

O Copiloto ganhou uma presença PERSISTENTE: um **Dynamic Island** flutuante
(`components/DynamicIsland.tsx`, montado em `app/panel/layout.tsx`) que acompanha o
usuário em TODAS as telas do painel após o onboarding (só aparece com território
configurado). Fechado é uma cápsula discreta; expandido vira chat, mostrando em tempo
real qual ferramenta o agente está consultando. Histórico em sessionStorage.

- **Backend** — `ai/agent.py`: agente LLM com **tool calling** (LiteLLM, formato
  OpenAI tools, até 4 rodadas). Ferramentas = serviços do Hub na MESMA sessão RLS do
  request: `repasses_visao_geral`, `propostas_listar`, `propostas_prazos`,
  `conformidade_resumo`, `obras_resumo`, `noticias_transferegov`,
  `pesquisar_propostas` (RAG). O agente só enxerga o território do tenant por
  construção; executor com erro devolve `{"erro": ...}` e nunca derruba o loop.
- **Degradação** — sem `llm_api_key`, roteador por palavra-chave
  (`escolher_tool_fallback`, ordem de prioridade em `_PRIORIDADE_FALLBACK`) executa a
  ferramenta mais provável e formata resposta legível (`_formatar_fallback`) — o
  island continua útil sem credencial.
- **Endpoint** — `POST /copilot/island` (SSE) em DUAS fases (`ai/agent.preparar`):
  a fase 1 roda o loop de tools com a sessão RLS do request viva e devolve os
  eventos `{"tool": nome}`; a fase 2 é um gerador da resposta final que NÃO toca
  no banco — o router o consome depois que a resposta HTTP já começou, então o
  texto pinta progressivamente (resposta pronta sai fatiada por `_fatiar`;
  rodadas esgotadas fazem stream real do LLM). O front renderiza os deltas ao
  vivo (`parcial`). Client web: `islandStream` em `lib/api/client.ts`.
- Adicionar ferramenta = nova entrada em `ai/agent.py::TOOLS` (descrição + JSON
  schema + executor + gatilhos de fallback); o front mostra o chip automaticamente
  (rotule em `DynamicIsland.tsx::TOOL_CHIP` e `TOOL_LABEL`).
- **Catálogo completo (22 tools)**: além das originais, o agente cobre
  `minhas_propostas` (favoritas da aba Acompanhamento), `proposta_detalhe`,
  `captacao_resumo`, `pareceres_plano`, `emendas_resumo`, `alertas_atualizacoes`,
  `monitoramentos_listar`, `pastas_listar`, `contatos_buscar`, `perfil_visao_geral`,
  `municipios_buscar`, `class_buscar` — e três de AÇÃO (por-tenant, reversíveis):
  `favoritar_proposta`, `alertas_varredura`, `alertas_marcar_lidos`. Cada tool
  respeita o módulo (§29) do seu eixo; a dimensão município recebe o recorte do
  painel por padrão.
- **Morph de atualização**: o island fechado MORFA quando há alerta de proposta
  não lido (badge âmbar com contagem, poll ~90s em `GET /alerts?nao_lidos`);
  expandido, um banner lista as atualizações com "marcar lidas" e link para a
  central. O botão ⟳ roda `POST /alerts/scan` (varredura) e alimenta o morph;
  respostas cujas tools mudam alertas recarregam o badge.
- **Voz**: ditado por Web Speech API (`SpeechRecognition`, pt-BR — o 🎙 preenche
  o campo e envia ao fechar a frase) e leitura das respostas por
  `speechSynthesis` (toggle 🔊 persistido; pergunta ditada é sempre respondida em
  voz). Sem suporte do navegador, os controles somem — o chat segue.
- **Harness próprio de tool calling** (`ai/agent.Harness` + `ai/harness.py`):
  LLM, executores e catálogo são bordas injetáveis — o MESMO loop de produção
  roda sem rede e sem banco nos testes (`test_island_harness.py`) e no CLI
  `python -m src.tools.harness_copiloto` (valida estrutura do catálogo, tabela
  de ouro do roteador de fallback e cenários simulados; sai 1 se algo falhar).

## 25. Rotas em INGLÊS (decisão travada) + Captação em tempo real

- **Todas as rotas são em inglês** — API v1 e páginas web. De-para principal:
  propostas→proposals · consulta-avulsa→proposals/live-search · repasses→transfers ·
  conformidade→compliance · obras→works · alertas→alerts (lido→read, varredura→scan) ·
  favoritos→favorites · pastas→folders · monitoramentos→monitors (buscas→searches) ·
  perfil→profile (visao-geral→overview, novidades→feed) · municipios→municipalities ·
  noticias→news · copiloto→copilot · planos→plans · admin/usuarios→admin/users ·
  convites→invites · fontes→sources · conhecimento→knowledge · aceitar-convite→accept-invite ·
  contatos→contacts (exportar→export, importar→import) · integracoes→integrations
  (provedores→providers, autorizar→authorize, senha-app→app-password).
  Páginas: painel→panel (captacao→funding, repasses→transfers, conformidade→compliance,
  obras→works, alertas→alerts, chat→copilot, conta→account), cadastro→signup,
  esqueci-senha→forgot-password, redefinir-senha→reset-password, verificar-email→verify-email.
  Campos de schema/payload seguem em pt (domínio); só as ROTAS são en.
- **Captação em TEMPO REAL**: `POST /proposals/live-search`
  (`services/consulta_avulsa.live_search`) — para cada município do perfil (ou o
  filtrado) × fonte de captação relevante (`CAPTACAO_FONTES`; recorte por
  fonte>área>fontes do perfil via `_fontes_alvo`), reusa o fluxo cache-first por fonte
  (fresco responde na hora; stale/miss vai à fonte via connector — API e/ou scraping) e
  devolve propostas filtradas + status por fonte (best-effort; falha vira status+sync_run).
  A página `app/panel/funding` dispara a busca a CADA mudança de filtro (debounce 500ms,
  descarte de resposta antiga) e mostra o estado da coleta. Exportar PDF saiu da UI
  (endpoint continua na API).

## 26. Meu painel com oportunidades ao vivo + aba Acompanhamento

- **Meu painel** mostra "Oportunidades disponíveis para o seu território": chama
  `POST /proposals/live-search {tipo: 'disponivel'}` no load (dados ao vivo das fontes,
  pós-onboarding), lista top-6 com ★ para favoritar direto e link p/ Captação.
- **Aba ★ Acompanhamento** (fixa) na Captação: lista as propostas FAVORITADAS completas
  via `GET /favorites/proposals` (`services/favoritos.listar_propostas`, join sob RLS —
  favorita fora do território não vaza). Favoritar em qualquer lugar (busca, painel,
  detalhe) adiciona aqui; a estrela remove. No modo acompanhamento os filtros/live-search
  ficam ocultos (a fonte é a lista de favoritas).

## 27. Connectors autocalibráveis (calibração contra as APIs vivas)

Erros reais de produção mostraram que rotas/colunas oficiais divergem do chute
estático. Os connectors críticos agora se AUTOCALIBRAM (com override manual no
painel admin quando preciso):

- **transferegov_ff**: a coluna de IBGE de `programa_beneficiario` é descoberta
  em runtime — override `transferegov_ff_ibge_field` > OpenAPI do PostgREST
  (Accept: application/openapi+json) > lista de candidatos (42703 → próximo);
  resultado cacheado por base_url. Fallback de IBGE 6 dígitos. Se
  `plano_acao`/`programa` recusarem a chave de ligação, degrada para o
  beneficiário puro (o programa disponível ainda vira proposta).
- **fpm**: rota descoberta via `metadata-catalog/` do ORDS + candidatos
  (`tt/transferencias`…), override `fpm_endpoint`. Envia os dois estilos de
  parâmetro (cod_ibge/ano e id_ente/an_exercicio) e SEMPRE refiltra no cliente
  pelo IBGE — linha sem coluna de IBGE compatível é descartada (nunca ingere o
  Brasil inteiro). Mapeamento de campos genérico (valor/data/descrição por
  palavra-chave; FUNDEB/PASEP/retenção → natureza dedução).
- **transferegov_esp / transferegov_voluntarias**: mesmo padrão do ff via
  helper compartilhado `connectors/_postgrest.py` — descoberta de ROTA e coluna
  de IBGE pelo OpenAPI do módulo (tabelas preferidas: plano_acao/convenio…),
  overrides `transferegov_esp_endpoint|_ibge_field` e
  `transferegov_voluntarias_endpoint|_ibge_field`, candidatos de coluna em 42703
  e fallback IBGE 6 dígitos; scraping segue como fallback quando a API cai.
- **siconfi/CAUC**: se `siconfi_csv_url` é página de dataset CKAN, resolve o
  recurso CSV real via `api/3/action/package_show` (preferindo 'cauc'; cache
  1h); colunas achadas por palavra-chave; delimitador ;/, autodetectado.
- **emendas**: o Portal da Transparência NÃO filtra por município — o connector
  pagina o ano (`ano`+`pagina`, cap 20 páginas) e refiltra por
  `localidadeDoGasto` com o nome do município resolvido via IBGE Localidades
  (`services/municipios.nome_uf_por_ibge`), sem acento + UF. Segue exigindo
  `emendas_api_key`.

## 28. Execução financeira do TransfereGov (empenhado por município/ano)

O relatório da Visão Geral do TransfereGov (22 colunas) agora é cidadão de
primeira classe — o gestor vê "quanto foi disponibilizado (EMPENHADO) ao meu
município e ainda não foi utilizado":

- **`propostas.execucao`** (jsonb, migration `c7d8e9f0a1b2`): valor_global/
  empenhado/liberado/pago, saldo_conta, ano, tipo_transferencia,
  ente_recebedor, natureza_juridica, datas de assinatura/vigência. Entra no
  hash de mudança (empenho novo → alerta) e no upsert. Fim de vigência vira
  prazo estruturado (alimenta /proposals/deadlines e o copiloto).
- **Normalizador** (`_montar_execucao`): aceita snake_case e os cabeçalhos do
  relatório ("Valor Empenhado", "Saldo em Conta"…), sem acento.
- **Fontes**: serpro (schema de extração calibrado às 22 colunas do painel) e
  transferegov_disc (CSV nacional SIconv/detru com mapeamento por
  palavra-chave + cache em memória 1h; incluído em CAPTACAO_FONTES).
- **Web Captação**: cards agregados (Transferências · Valor global · Empenhado ·
  **Empenhado a utilizar** [destaque] · Pago · Saldo em conta), filtro por ANO,
  colunas Valor global/Empenhado (com ponto verde quando há verba parada).
- **Web detalhe**: seção "Execução financeira — TransfereGov" com barra de
  progresso empilhada (pago ⊂ liberado ⊂ empenhado sobre o global), os 6
  valores, vigências e ente recebedor.

## 29. Módulos da plataforma — ligar/desligar eixos pelo painel admin

Cada eixo do produto (as lentes do menu profile-centric da seção 19) é um **módulo**
que o admin liga/desliga em **runtime**, sem redeploy e sem remover código. Serve para
lançar o Hub só com o que está maduro e reativar o resto quando a fonte estiver calibrada.

**Estado inicial (decisão de produto):** `captacao`, `recebidos` e `copiloto` **ativos**;
`conformidade` e `obras` **desativados** — a implementação continua no repositório
(connectors, migrations, serviços, telas), apenas não é exposta.

- **Registro** — `services/modulos.py::MODULOS` (chave, label, descrição, `padrao`).
  O estado vive na tabela `configuracoes` (platform-level) sob a chave `modulo_<chave>`
  com valor `on`/`off`; sem linha no banco vale o `padrao` do registro (nenhuma migration
  necessária). Adicionar um módulo = mais uma entrada nesse registro.
- **Guard de API** — `services/modulos.require_modulo(chave)` é dependency de router:
  módulo desligado → **404 `MODULO_DESATIVADO: <chave>`** em todo o eixo. Aplicado em
  `transfers` (recebidos), `compliance`, `works` e `copilot`; em `proposals` o gate é
  POR ENDPOINT — só a exploração (§40): as leituras de cache do painel ficam livres.
  O guard roda ANTES da autenticação (dependency de router), então o eixo simplesmente
  não existe enquanto desligado.
- **Endpoints admin** (`is_superuser`): `GET /admin/modules` (catálogo + estado efetivo)
  e `PUT /admin/modules` (`{chave, ativo}`). Router `api/v1/admin_modulos.py`.
- **Perfil** — `GET /profile` passa a devolver `modulos` (lista dos ativos) e
  `GET /profile/overview` agrega as dimensões pela regra da §40 (módulo ativo OU
  dado no cache; sem link quando o módulo está desligado).
- **Web** — `app/admin/modules` (toggle por módulo, no shell admin da seção 24); o menu
  de `app/panel/layout.tsx` filtra os itens por `perfil.modulos`;
  `components/ModuloGate.tsx` cobre o acesso direto por URL às telas de eixo desligado
  (explica em vez de mostrar tela vazia).

## 26b. Filtros de captação (benchmark) + resumo + emendas parlamentares

Paridade de FILTROS com as plataformas concorrentes de captação, sem abrir mão da
navegação profile-centric (§19): as fontes continuam sendo detalhe de ingestão — o que
mudou é a granularidade do recorte sobre o território.

- **Dimensões de filtro da captação** (`services/propostas.py`): busca livre `q`
  (programa/órgão/código, ilike sobre título/objeto/órgão/modalidade/id/nº), `modalidade`
  (tipo de instrumento), `orgao`, `situacao`, `natureza_juridica`, `qualificacao`, `ano`,
  `tipo` (§23), faixa de valor e `ordenar`
  (`recentes|prazo|prazo_distante|nome|orgao|valor`). SQL para o que é coluna; jsonb/
  derivados (natureza, qualificação, ano, tipo) filtram em Python — o recorte já é do
  território pelo RLS, então o conjunto é pequeno.
- **Natureza jurídica** = quem pode propor. `classificar_natureza_juridica` faz de-para
  por palavra-chave de `execucao.natureza_juridica` (texto livre da fonte) para os slugs
  `estadual_df|municipal|consorcio|empresa_publica|osc|outros` — calibrável em
  `_KW_NATUREZA`. **Qualificação** mapeia `execucao.tipo_transferencia`.
- **Facetas** — `GET /proposals/facets` devolve, por dimensão, as opções que EXISTEM no
  recorte com contagem; a contagem de cada dimensão ignora o filtro dela mesma (senão o
  dropdown ficaria preso na opção escolhida). `POST /proposals/live-search` já embute as
  facetas na resposta (evita 2ª chamada a cada tecla).
- **Resumo** — `GET /proposals/summary`: cards (valor conveniado/desembolsado/empenhado/
  a utilizar, convênios iniciados e em execução, oportunidades abertas), série
  aprovado × desembolsado por ano, pipeline por situação e convênios vigentes com % de
  desembolso. Web: `app/panel/funding/summary`.
- **Relatório** — `GET /proposals/report.csv` e `GET /transfers/amendments/report.csv`
  (CSV `;` + BOM, abre no Excel) exportam exatamente o recorte da tela.
- **Emendas parlamentares** — lente sobre os repasses com `emenda=True`, não uma aba de
  fonte: `GET /transfers/amendments/summary` (cards empenhado/pago e % executado, evolução
  anual, distribuição por modalidade e por área/função, ranking de parlamentares, lista
  detalhada e `opcoes` dos filtros). Filtros: modalidade, ano, parlamentar, órgão, busca.
  O connector `emendas` passou a guardar em `detalhe` o que a tela precisa (parlamentar,
  partido, `tipoEmenda`, função/subfunção, ano, empenhado/liquidado/pago). Web:
  `app/panel/transfers/amendments`. As opções dos dropdowns vêm do universo do território
  (sem os filtros aplicados) — escolher um parlamentar não esvazia a lista.
- **Web (captação)** — barra com busca, chips de natureza jurídica, chips
  cadastrada/disponível, dropdowns por faceta (modalidade/órgão/qualificação/situação/
  ano/fonte), ordenação, **filtros ativos** com remoção individual e "limpar tudo", e
  "Baixar relatório". `PropostaRead` ganhou os computados `natureza_juridica`,
  `prazo_final` e `dias_restantes` (contador de prazo na lista).

## 29. Guarda de segredo no boot (produção)

`JWT_SECRET`/`JWT_REFRESH_SECRET` têm padrão versionado no `.env.example` (dev
local sobe sem configurar nada). Em produção isso permitiria forjar token de
qualquer usuário, então `core/seguranca_boot.verificar_segredos` roda no
`lifespan` ANTES de tudo:

- **dev** (APP_BASE_URL com localhost/127.0.0.1/.local) → só avisa no log;
- **produção** (domínio público) → **RuntimeError e o boot para**, com a
  instrução exata (`openssl rand -hex 32` em cada variável);
- válvula consciente p/ homologação atrás de domínio: `PERMITIR_SEGREDO_PADRAO=true`
  (mantém o aviso).

Trocar os segredos invalida as sessões vigentes uma vez — comportamento esperado.

## 30. Recorte de DUAS fontes + scraping como 2ª fonte de verdade (decisão travada)

Enquanto as demais fontes não estão calibradas contra as APIs vivas, o produto opera
com **TransfereGov + FNS**. As outras (FPM, emendas, FNDE, SISMOB/SIMEC/CAIXA, Siconfi)
continuam no repositório — connectors, migrations, serviços e telas — apenas fora do
recorte. Ligar de volta = uma linha em `services/fontes.py`; o core não muda.

- **Registro** — `services/fontes.py` é a fonte de verdade: `GRUPOS` (o que o usuário
  escolhe: `transferegov`, `fns`), `HABILITADAS` (connector ids em operação),
  `CAPTACAO` (produz propostas) e `RECEBIDOS` (produz repasses). `expandir()` traduz
  grupo → connector ids na entrada do onboarding, então todo o resto do sistema
  segue falando connector id. `CAPTACAO_FONTES` (consulta_avulsa), `FONTES_CAPTACAO`/
  `FONTES_RECEBIDOS` (primeiro_sync), `FONTES_PADRAO` (router de transfers) e
  `AREA_FONTES` (perfil) derivam daí — não existe mais lista de fontes solta.
- **`serpro` é TransfereGov**: apesar do `source_id`, o connector coleta o painel da
  **Visão Geral do TransfereGov** (`dd-publico.serpro.gov.br/.../TransferegovbrVisaoGeral.html`);
  o SERPRO só hospeda. Por isso está no grupo `transferegov` e em `CAPTACAO`.
- **Onboarding** oferece só os dois grupos (com descrição), pré-marcados pelas áreas.
  TransfereGov serve todas as áreas (não é setorial); FNS entra com saúde.

**Scraping deixou de ser fallback.** A §5 (coleta combinada) agora é real:
`connectors/_combinada.py` roda API e scraping **em paralelo** (`coletar`) e pareia as
linhas pelo número da transferência só por dígitos (`aglutinar` — "123456/2024" casa com
1234562024). O payload de scraping viaja no `raw` sob `_scrape`, e
`ingestion/merge.py::merge_record` normaliza os dois lados e funde com a precedência de
sempre (API vence em id/valor/data; scraping vence em situação/pendências/movimentação),
gravando `proveniencia` por campo. Linha que só existe no scraping entra sozinha — a
página conhece transferência que a API ainda não publicou. Aplicado em `serpro`;
`consulta_avulsa` usa `merge_record` no lugar de `merge(normalize(...), None)`.

**Scraping local (sem serviço externo).** O facade (`scraping/scraper.py`) passou a ter
quatro providers, nessa ordem no modo `auto`: `crawl4ai_local` → `playwright` →
`crawl4ai` (servidor) → `firecrawl`. Os dois primeiros rodam Chromium no próprio
container (extra opcional `scraping` no pyproject: `uv sync --extra scraping`), o que
destrava as páginas JS-pesadas sem chave paga nem container extra.
- `scraping/tabelas.py` é a extração: lê `<table>` **e grid ARIA** (`role="grid"/"row"/
  "columnheader"` — como o Qlik renderiza) com parser de pilha, e casa cabeçalho com o
  campo do JSON Schema do connector por texto normalizado ("Valor Empenhado" →
  `valor_empenhado`; `numero` → "Nº Transferência" pela `description`). Determinístico,
  sem LLM, sem custo por página; o que não casou fica em `_linha` para calibração.
- `scraping/playwright.py` vence virtualização rolando o grid até parar de aparecer
  linha nova, e cai para o Chromium do sistema (`CHROMIUM_EXECUTABLE_PATH`,
  `/opt/pw-browsers/chromium`…) quando o browser do pacote não está baixado.
- Crawl4AI **não levanta** em falha de navegação (devolve `success=False`): o provider
  converte isso em exceção, senão "não abri a página" viraria "a fonte não tem
  registros" e o gestor veria painel vazio como se fosse verdade.
- Chaves novas no painel admin (categoria scraping): `scraping_crawl4ai_local`,
  `scraping_playwright` (`on`/`off`) e `scraping_provider` aceitando os quatro nomes.
- `services/config.resolver` passou a degradar para o `.env` quando o Postgres não
  responde (o painel só SOBRESCREVE o `.env`) — banco fora do ar não derruba ingestão.
- **Dockerfile**: `ARG COM_SCRAPING=1` instala o extra + `playwright install --with-deps
  chromium` (~500MB). `--build-arg COM_SCRAPING=0` monta a imagem enxuta.

**Probe de fontes** — `python -m src.tools.probe_fontes <ibge> [--fonte X] [--json]`:
bate nas fontes REAIS e relata por fonte se respondeu, quantos registros e QUAIS campos
vieram (é o que se calibra). Não precisa de banco nem da API no ar; sai com código 1 se
alguma falhar. Calibrar connector é trabalho empírico — isto substitui descobrir pelo
`sync_runs` depois do deploy.

## 30b. FNS — API do ConsultaFNS como fonte primária (coleta combinada)

O connector `fns` deixou de ser só-scraping: sem scraper configurado a fonte ficava
morta (`ScraperNotConfigured`). Agora o backend REST do portal ConsultaFNS
(consultafns.saude.gov.br) é a fonte PRIMÁRIA e o scraping da página segue como 2ª
fonte de verdade — os dois rodam em paralelo (`_combinada.coletar`) e o resultado é
fundido pareando pela PORTARIA/OB (só dígitos): API vence em id/valor/data/documento,
scraping vence nos descritivos (`descricao`/`categoria`), origem por campo em
`raw["_proveniencia"]` (o `normalizer_repasse` respeita o hint; padrão segue `api`).
Linha que só o scraping conhece entra sozinha.

- **Autocalibração (§27)**: rota do backend não é fixa — override `fns_api_endpoint`
  (painel admin) > cache > candidatos (`repasse/consultar`, `repasse`,
  `pagamento/consultar`…). Parâmetros nos dois estilos (código 6 dígitos e IBGE 7);
  quando a resposta ecoa coluna de IBGE/município há refiltro estrito no cliente
  (nunca ingere o Brasil inteiro); resposta sem a coluna é aceita porque a consulta
  já foi por município. Casamento de campo por palavra-chave com normalização
  camelCase→snake (`vlRepasse` → `vl_repasse`) — cobre camelCase, snake e CAIXA ALTA.
- **Config** (categoria fonte): `fns_api_url` (default
  `https://consultafns.saude.gov.br/recursos/`), `fns_api_endpoint` (vazio =
  candidatos) e `fns_consulta_url` (página, scraping). `health_check` = API de pé
  (2xx/4xx na raiz) OU scraper habilitado.
- **Validação**: unit tests em `test_calibracao_connectors.py` (seção FNS); ao vivo,
  `python -m src.tools.probe_fontes <ibge> --fonte fns` de uma máquina com saída para
  gov.br (o sandbox de CI/agente pode bloquear) — é onde se calibra rota/campos reais.

## 31. Agenda de contatos + sincronização com Google/Apple/Outlook

Rede de pessoas do gestor (gabinetes, secretarias, técnicos, fornecedores) dentro do Hub,
**sincronizada nos dois sentidos** com a agenda que ele já usa no celular. Dado PESSOAL
por-tenant (RLS `FOR ALL` por `usuario_id`, como `pastas`) — não é cache público.
Módulo desligável pelo painel admin (`contatos`, §29), rotas em inglês (§25).

- **Tabelas** (migration `b41c7de90a12`): `contatos` (nome/sobrenome, organização, cargo,
  `emails`/`telefones`/`enderecos` jsonb, `tags`, `municipio_ibge`, `origem`, `chave_dedup`,
  `hash_conteudo`, `arquivado`) · `integracoes_contatos` (uma linha por conta conectada:
  provedor, conta, status, `direcao`, `credenciais` **cifradas**, `sync_token`, última sync,
  último erro) · `contato_vinculos` (de-para local↔remoto com `etag` e `hash_sincronizado`;
  escopo herdado da integração, como `pasta_propostas`).
- **Provedores** (`integrations/contatos/`, Protocol + registry no molde dos connectors):
  `google.py` (People API, delta por `syncToken`) · `microsoft.py` (Graph, delta por
  `deltaLink`) · `carddav.py` (Apple/iCloud e CardDAV genérico — Nextcloud/SOGo —, delta por
  CTag, redirect refeito na mão para não perder o Basic) · `vcard.py` (codec vCard 3.0, usado
  pelo CardDAV e pelo import/export `.vcf`) · `oauth.py` (authorization code + refresh).
  Novo provedor = novo módulo com o mesmo Protocol; o motor de sync não muda.
- **Motor** (`services/contatos_sync.py`): casamento por vínculo → `chave_dedup` (e-mail >
  telefone > nome+organização) → criação. Três hashes (local, remoto, `hash_sincronizado`)
  decidem quem mudou; **os dois lados mudaram → merge**, ninguém perde e-mail/telefone/tag.
  Remoção é arquivamento (tombstone) para propagar o delete; ausência só conta como remoção
  quando a leitura foi completa (num delta, não). Erro de provedor → `status=erro|expirada` +
  `sync_runs`, nunca 500. `ingestion/normalizer_contato.py` faz canonização/dedup/hash/merge.
- **Endpoints**: `GET/POST /contacts`, `GET/PATCH/DELETE /contacts/{id}` (DELETE arquiva),
  `GET /contacts/export` (.vcf), `POST /contacts/import` ·
  `GET /integrations/contacts/providers` · `GET /integrations/contacts` ·
  `POST /integrations/contacts/{provedor}/authorize` (URL de consentimento) ·
  `POST /integrations/contacts/callback` · `POST /integrations/contacts/{provedor}/app-password`
  (Apple/CardDAV) · `PATCH/DELETE /integrations/contacts/{id}` ·
  `POST /integrations/contacts/{id}/sync` e `POST /integrations/contacts/sync`.
- **Config (painel admin, categoria `integracoes`)**: `google_client_id/secret`,
  `microsoft_client_id/secret`, `microsoft_tenant`, `apple_carddav_url`. Sem elas o provedor
  aparece **indisponível** (degrada como Firecrawl/LLM/Uniq) — e o `.vcf` continua servindo
  de rota manual. Redirect URI dos apps OAuth: `{app_base_url}/integrations/callback`.
  Segredos usam o Fernet compartilhado em `core/crypto.py` (o `services/config` passou a usá-lo).
- **Job**: `jobs/contatos.sync_contatos_todos()` (cron n8n) roda cada usuário na sua sessão
  RLS, best-effort, e limpa tombstones já propagados.
- **Web**: `app/panel/contacts` (agenda + CRUD + busca, agendas conectadas com status/direção,
  sincronizar, importar/exportar .vcf) e `app/integrations/callback` (conclui o OAuth). Item
  "Agenda de contatos" no menu profile-centric — é uma lente de pessoas sobre o território,
  não uma aba por plataforma (§19 continua valendo).

## 32. Curadoria (pílulas de categoria) + filtros e leitura dos campos da fonte

Três problemas da tela de captação, resolvidos na camada certa de cada um.

- **Pílulas de categoria (IA + determinístico)**: taxonomia FECHADA em
  `ai/categorias.py` (saúde, educação, infraestrutura, saneamento, mobilidade, cultura,
  esporte, assistência social, agricultura, meio ambiente, segurança, habitação, turismo,
  tecnologia, gestão). Duas camadas sobre ela: `classificar()` (palavra-chave, **sem rede**,
  casamento por palavra — `\bTERMO\b`, ou `\bTERMO` com `*`; sem isso "cultura" casa dentro de
  "agriCULTURA") e `ai/resumo.gerar_curadoria()` (LiteLLM: resumo + categorias refinadas numa
  chamada só, com fallback para o determinístico em qualquer falha). Coluna
  `propostas.categorias_ia` jsonb (migration `e1a2b3c4d5f6`) — dado DERIVADO, fica **fora** do
  `_UPSERT_FIELDS` para um re-sync não apagar a curadoria. Jobs em `jobs/curadoria.py`:
  `classificar_pendentes` (roda no fim de toda coleta, dentro do request) e `curar_com_ia`
  (lote pequeno, só no 1º sync/cron — nunca no request). A API entrega
  `PropostaRead.categorias` = `[{slug, rotulo}]`, pronta para exibir e filtrável por slug.
  Adicionar categoria = um item em `CATEGORIAS`; filtro, faceta, CSV e pílula acompanham.
- **Filtros do painel (além de ano)**: novas dimensões `municipio`, `uf`, `mes` e `categoria`
  em `services/propostas._DIMENSOES` — somadas a fonte, modalidade, órgão, situação, natureza
  jurídica, tipo de transferência (`qualificacao`) e tipo. `mes_de()` usa o mês do **prazo
  final**; sem prazo, o da atualização na fonte. `facetas()` não manda mais nenhuma dimensão
  para o SQL: o recorte base é território (RLS) + área/busca/faixa de valor, e cada dimensão é
  contada ignorando o próprio filtro (senão o dropdown de município fecharia em cima da opção
  escolhida). Dimensão pode ser **multivalorada** (`categoria`). Ano/mês ordenam
  cronologicamente, não por contagem.
- **Campos de extensão longa**: `components/TextoExpansivel.tsx` recorta o valor em N linhas e
  só mostra **Ampliar** quando há corte de verdade (medido no DOM, não por contagem de
  caracteres); ampliado, o texto rola dentro de si em vez de esticar a página. Em
  `app/panel/funding/[id]`, "Dados completos da fonte" separa campos curtos (grade) de longos
  (linha inteira) e ganha **Ampliar tudo**; `objeto` e `movimentacao` usam o mesmo componente.
- **TÍTULO com teto de caracteres** (`components/TextoLimitado.tsx` + `lib/format.recortarTexto`):
  as fontes não separam título de descrição — o `objeto` vira título e chega com o projeto
  inteiro dentro (mais de 2 mil caracteres num edital de cultura). Ampliar in loco não serve
  aqui: no cabeçalho do detalhe o título empurrava valor, empenho e prazo para fora da dobra,
  e na lista esticava a linha por meia tela. O corte é por CARACTERE (previsível em qualquer
  largura, ao contrário do clamp de linhas do `TextoExpansivel`), sempre em palavra inteira, e
  o inteiro abre em **modal** — que é onde ele pode ocupar o espaço que precisa, com "copiar
  texto". Aplicado em `panel/funding/[id]` (limite 180), `panel/funding` e
  `panel/my-proposals` (110). O gatilho "ver completo" fica FORA do que `envolver` monta: nas
  listas o trecho vive dentro de um `<Link>` e botão dentro de âncora é HTML inválido (mesma
  razão do `copiavel={false}` do `NumeroProposta`, §44). Nos **cards** — feed do Meu painel e
  central de alertas — o teto é **80** e sem gatilho: a linha INTEIRA é o `<Link>` do registro,
  então não cabe botão dentro dela, e o texto completo está a um clique, no detalhe. O
  `truncate` continua como segunda rede para a tela estreita.
- **Modal** (`components/Modal.tsx`) é a janela sobreposta do app — portal no `body` (dentro
  da árvore, o `overflow` das tabelas de captação recortaria a janela e o trilho lateral
  passaria por cima), Esc, clique no FUNDO (não no arrasto de seleção), Tab preso e foco
  devolvido a quem abriu. `bg-card` sobrepõe o vidro translúcido do `.card`: sobre o fundo
  escurecido, o texto de trás vazaria para dentro da janela.
- **CAIXA ALTA das fontes**: `lib/format.humanizarCaixa()` normaliza só na APRESENTAÇÃO
  ("MTUR/SECULT - ALDIR BLANC - MUNICÍPIOS" → "MTUR/SECULT - Aldir Blanc - Municípios";
  "FUNDO_A_FUNDO" → "Fundo a Fundo"). Texto já em caixa mista passa intacto; siglas e códigos
  numéricos são preservados. O dado gravado continua idêntico à origem — a conferência é pelo
  link "Fonte oficial ↗".

## 33. Recorte de território — filtrar QUAIS dos municípios do perfil ver agora

O onboarding grava N municípios; o painel precisava responder "quais desses eu quero
olhar neste momento". O recorte é **global e um subconjunto** (não "um município ou
todos"), vale para TODAS as lentes do menu profile-centric (§19) e nunca amplia
visibilidade — o RLS segue sendo o limite: pedir um IBGE fora do território devolve vazio.

- **Contrato** — `municipio` virou parâmetro **repetível** em toda leitura:
  `GET /proposals` (+`/facets`, `/summary`, `/report.csv`, `/deadlines`), `GET /transfers`
  (+`/overview`, `/amendments/summary`, `/amendments/report.csv`), `GET /works` (+`/summary`),
  `GET /compliance`, `GET /profile/overview` e `GET /profile/feed`
  (`?municipio=2611606&municipio=3550308`; um valor só continua valendo). Em corpo JSON:
  `POST /proposals/live-search` usa `municipios_ibge: []` (era `municipio_ibge`) e
  `POST /copilot/island` aceita `municipios`.
- **Serviços** — `services/_territorio.py` é o de-para único: `ibges()` normaliza
  `str | lista | None` (dedup, sem vazios) e `filtrar()` aplica o `IN` na query. Todos os
  serviços de leitura (`propostas`, `repasses`, `obras`, `conformidade`, `perfil`,
  `consulta_avulsa`) tipam o filtro como `Municipios`. Em `propostas.facetas` a dimensão
  multi-seleção casa por **interseção** (OU dentro da dimensão, E entre dimensões) e a
  dimensão município continua ignorando o próprio filtro — senão não daria para trocar
  de recorte pelo dropdown.
- **Perfil** — `visao_geral`/`novidades` recebem `municipios_filtro`; a visão geral devolve
  em `municipios` **o recorte** (o cabeçalho mostra o que está sendo visto, não todo o
  território).
- **Copiloto** — `ai/agent.executar(..., municipios=...)` injeta o recorte como padrão das
  ferramentas (o LLM só sobrepõe pedindo um município explícito) e o descreve no system
  prompt. O island flutua sobre o painel: responde sobre o mesmo conjunto que está na tela.
- **Web** — `lib/territorio.tsx` (`TerritorioProvider` + `useTerritorio`) carrega o perfil
  UMA vez para todo o painel, guarda a seleção em `localStorage` (`hub_territorio_ativo`,
  vazio = todos) e poda IBGEs que saíram do onboarding. `components/TerritorioFiltro.tsx`
  fica no trilho lateral, junto do território: multi-seleção com "todos", atalho "só este",
  busca a partir de 8 municípios e chips do recorte ativo. As telas leem `selecionados` e
  mandam `paramMunicipio(...)` na chamada; o município **saiu** dos filtros locais da
  Captação (era single-select por aba) — é escolha global agora.

### 33b. Recorte de ORIGEM DO RECURSO — o irmão do território (decisão travada)

A outra metade do recorte global do painel: o território diz DE ONDE (município), a
origem diz DE QUAL FONTE veio o registro. Mesmo desenho da §33 — vive no trilho lateral,
é multi-seleção (vazio = todas), persiste por navegador e **nunca amplia visibilidade**
(o RLS e o perfil seguem sendo o limite; o filtro só estreita).

- **O vocabulário é o GRUPO, não o connector** (§30): o gestor marca "TransfereGov" ou
  "FNS"; a expansão grupo → connector ids acontece na API (`services/fontes.py`:
  `Fontes`/`connectors()`/`condicao()`/`filtrar()`, espelho de `_territorio.py`). O front
  tinha uma lista FIXA de origens com fontes fora do recorte da v1 e com o TransfereGov
  reduzido a `transferegov_ff` — marcar a origem filtrava por um id que quase nenhum
  registro tinha, e a tela "não fazia nada". O catálogo agora vem do perfil
  (`GET /profile` → `origens`), então só aparece o que aquele usuário tem.
- **Contrato** — `fonte` é parâmetro REPETÍVEL (grupo ou connector id) em
  `GET /proposals` (+`/facets`, `/summary`, `/report.csv`), `GET /transfers`
  (+`/overview`, `/amendments/summary`, `/amendments/report.csv`), `GET /profile/overview`,
  `GET /profile/feed`; em corpo JSON, `POST /proposals/live-search` já o aceita como lista.
  Na captação ao vivo, origem escolhida que não produz proposta (o connector de repasse
  do FNS) sai da rodada em silêncio; id que não é connector nenhum segue e vira status de
  erro — pedido por fonte inexistente não pode responder "nada encontrado".
- **Um filtro, uma tela só, nunca**: o recorte valia apenas em `panel/transfers` (e ali
  peneirava o feed no CLIENTE, com o "Total Pago" continuando a somar a origem tirada da
  tela). Agora entra na CONSULTA e vale para todas as lentes; o dropdown "Fonte" local da
  Captação **saiu** (mesma disciplina do município na §33 — filtro em dois lugares
  dessincroniza).
- **Onde o recorte NÃO se aplica**: conformidade (Siconfi/CAUC) e obras (SISMOB/SIMEC/
  CAIXA) não saem do catálogo de origens do gestor; aplicar o filtro nelas as zeraria
  sempre, o que é mentira, não filtro.
- **Web** — `lib/origem.tsx` (`OrigemProvider` + `useOrigem` + `paramFonte`, chave
  `hub_origem_recurso`) e `components/OrigemRecursoFiltro.tsx`, que **não se desenha** com
  menos de duas origens (chip que não muda a tela lê como controle quebrado).
- **Fonte na tela sai NOMEADA** (§35): `services/fontes.LABELS_CONNECTOR` e o espelho
  `lib/fontes.ts::rotuloFonte` — `transferegov_disc` é id de integração; o gestor lê
  "TransfereGov — Discricionárias". `NovidadeItem.fonte_rotulo` leva o nome pronto no feed.
- **A linha do feed tem UMA margem**: a coluna de ações (★ + espelho) existe em toda
  linha, mesmo nas de repasse, que não têm nenhuma das duas — sem ela o item do FNS
  começava colado na borda e a lista tinha duas margens esquerdas. O feed também passou a
  nomear o município (§35 — o repasse costuma chegar da fonte sem ele) e a esconder a
  descrição que só repete o rótulo da fonte.
- Regressão: `tests/test_filtro_origem.py` (normalização pura + captação, facetas,
  recebidos e Meu painel sob a mesma escolha de origem).

## 34. Espelho da proposta em PDF — atalho de exportação (compartilhar)

A rota de PDF existia desde a §17, mas sem porta na UI (a §25 tirou o botão) e o
documento era uma tabela cinza de 11 linhas. Agora é o **espelho**: a proposta
diagramada com a identidade do Hub, a UM clique, onde quer que ela apareça.

- **`services/pdf.py`** (reescrito) monta o mesmo conteúdo da tela de detalhe:
  banda da marca (abyss + `brand-dot` em gradiente lime→aqua + fio de gradiente),
  faixa de destaque (valor e prazo, os dois dados que decidem a ação de hoje),
  barra empilhada da execução financeira (pago ⊂ liberado ⊂ empenhado sobre o
  global) com legenda nas cores dos segmentos, pílulas de categoria/tipo, prazos e
  pendências com tom de urgência (mesma escada de `lib/format.ts::tomPrazo`),
  dados gerais e situação/movimentação. Rodapé com "página X de Y" (canvas de duas
  passadas) e data de emissão em toda página.
- **Paleta e tipografia**: tokens do tema CLARO de `globals.css` (o espelho é
  impresso e reencaminhado, nunca segue o tema escuro). Só fontes Type1 embutidas
  no reportlab — a imagem da API é `python:3.12-slim`, sem nenhuma TTF; o "mono"
  dos rótulos é reproduzido com caixa alta + `charSpace`. **Atenção**: `Tc` é
  estado GRÁFICO do PDF — sem zerar depois de desenhar com tracking, a banda vaza
  espaçamento para a página inteira e todo o texto transborda os cards (o layout
  fica certo e o desenho, errado).
- **Tetos de conteúdo** (`_MAX_*`): um card é UMA célula de tabela e não se parte
  entre páginas; sem teto, um `objeto` de 8 mil caracteres ou 40 pendências
  derrubam a exportação inteira com `LayoutError`. Os limites saem da largura de
  cada bloco e todo corte se declara ("trecho abreviado") — nada some em silêncio.
- **`services/texto.py`**: `humanizar_caixa` — espelho em Python do
  `lib/format.ts::humanizarCaixa`, para o PDF não sair gritando enquanto a tela
  não grita.
- **Endpoint**: `GET /proposals/{id}/pdf` ganhou nome de arquivo legível
  (`espelho-091234-2024-mossoro.pdf`), `?inline=true` (visualizar em vez de
  baixar) e `Cache-Control: no-store` (o documento carrega a data de emissão).
- **Web** — `components/BotaoEspelho.tsx` é o atalho único: no celular abre a
  folha nativa de compartilhamento com o PDF anexado (`navigator.share` com
  `canShare({files})`), no desktop baixa. Formato `botao` no cabeçalho do detalhe
  (com **atalho de teclado "P"**, ignorado quando o foco está num campo) e
  `icone` nas listas — Captação, Minhas propostas e feed do Meu painel. Cliente:
  `exportarEspelhoProposta` em `lib/api/client.ts` (lê o nome do
  `Content-Disposition`).

### 34b. O espelho leva o ANDAMENTO (e nada de plumbing) — decisão travada

Duas correções ao documento, vindas do uso: ele saía sem o que a tela mostra e
com o que a tela esconde.

- **O espelho é o espelho da TELA.** `gerar_pdf_proposta` recebe
  `pdf.Complementos` (andamento, empenhos + resumo, emendas) e desenha as três
  seções na MESMA ordem do detalhe. Quem lê o banco é o router
  (`api/v1/propostas.py::_complementos`, via `services/andamento`) — o serviço de
  PDF é síncrono e só diagrama. A leitura é a de sempre, cache-first com coleta
  na fonte quando o cache está vencido, e **best-effort**: cada eixo em seu
  `try/except`, porque fonte fora do ar não pode impedir a exportação. Sem isso o
  gestor via parecer, empenho e parlamentar autor na tela, encaminhava o espelho
  e a outra ponta recebia um PDF que não tinha nada daquilo.
- **Fora do documento: plumbing.** Saíram a seção "Conferência e proveniência"
  (com o QR e o link da fonte), o anexo "Dados completos da fonte" (dump do
  registro bruto), o "Identificador na fonte", o campo "Fonte", a URL de origem
  no rodapé e o nome da fonte de dados no cabeçalho. O espelho circula fora do
  painel: proveniência campo a campo, id de integração e instrução de
  administração não são assunto de quem recebe. O que referencia a proposta
  continua no cabeçalho — número, data de criação e órgão concedente (§35).
- **Listas longas em cards de poucas linhas** (`_cards_de_linhas`): um card é uma
  célula e não se parte entre páginas — 24 passos num card só derrubariam a
  geração. As linhas são distribuídas por igual entre os cards (6 passos viram
  3+3, não 5+1), e os tetos (`_MAX_EVENTOS`, `_MAX_EMPENHOS`, `_MAX_EMENDAS`)
  declaram o que ficou de fora.
- **Empenho sai LÍQUIDO** das anulações também aqui (§43): documento devolvido
  que continuasse somando diria que há recurso reservado onde não há.

## 35. Hierarquia de dado na exibição (decisão travada)

Complemento direto da seção 19: se a navegação parte do PERFIL, **o dado também
tem que se apresentar assim**. Em toda superfície de saída — header de detalhe,
listas, PDF, alerta de WhatsApp, contexto do LLM — vale a mesma ordem:

1. **MUNICÍPIO** — sempre primeiro, sempre pelo **nome** (`São Paulo/SP`).
2. **Objeto** do registro (título da proposta, nome da obra, o que o requisito exige).
3. **Números fortes** — valor e o **EMPENHO** (é o que diz se o recurso saiu do
   papel). Ficam na faixa de destaque, não numa grade secundária.
4. **Referência da proposta** — **nº da proposta** (`14275/2026`), **data de
   criação** e **órgão concedente**. É por eles que o gestor chama a proposta e
   é o que ele digita no portal da fonte para conferir: são dados de CABEÇALHO.
5. **Identificadores internos** — `id_externo`, nº do item do CAUC, UUID. Esses
   sim são **secundários**: pequenos, em mono, cinza, no fim.

**Referência ≠ identificador.** O nº da proposta é *linguagem do gestor*; o
`id_externo` é *plumbing da integração*. A primeira versão desta seção tratou os
dois como a mesma coisa e rebaixou o número junto com o UUID — errado.

**Campos da fonte em CAIXA ALTA**: `ingestion/normalizer._ci()` adiciona alias
minúsculo às chaves do registro bruto antes do de-para (sem sobrescrever chave já
existente). Sem isso, fonte com cabeçalho maiúsculo — o CSV do SIconv/detru manda
`NR_PROPOSTA`, `DIA_PROPOSTA`, `DESC_ORGAO` — não casava com nenhum candidato e o
campo chegava vazio à tela. Ao ligar uma fonte nova, conferir isto ANTES de
suspeitar do connector.

**`data_proposta`** (migration `f2b3c4d5e6a7`) é quando a proposta foi criada na
fonte; **não** confundir com `data_atualizacao_fonte` (quando a fonte mexeu no
registro). Entra no hash de mudança e no `_UPSERT_FIELDS`.

**O código IBGE nunca lidera** — é desambiguador, entra como linha de apoio
(`IBGE 3550308`). E **identificador nunca vira título**: fallbacks de `titulo`
param no objeto, nunca em `id_externo`.

**Resolução do nome** (`services/municipios.py`, metade "saída"): (1) o que a
fonte trouxe → (2) o território do usuário (`municipios_interesse`, sob RLS) →
(3) UF derivada do prefixo do IBGE (offline). Sem nome algum, `rotulo()` degrada
para `Município 3550308 (SP)` — rotulado, nunca um número solto. `enriquecer()`
completa `municipio_nome`/`uf` só na resposta (`model_copy`): não persiste nem
suja o ORM. Aplicado em propostas, repasses, obras e conformidade.

O front tem o par equivalente em `lib/format`: `municipioPrincipal()` e
`municipioSecundario()` — a regra mora neles, não num `municipio_nome ??
municipio_ibge` repetido por tela.

**Empenho** reaproveita a execução financeira que já vem do TransfereGov
(`execucao.valor_empenhado/liberado/pago/global`) — não há coluna nova. O que
mudou é o lugar: subiu para a faixa de destaque do detalhe, com "empenhado a
utilizar" (empenhado − pago) como linha de apoio.

**Casos mapeados e corrigidos** (checklist para telas novas):

| Onde | Antes | Agora |
|---|---|---|
| `panel/funding/[id]` | h1 = título, com fallback para `id_externo`; município em linha cinza de apoio | h1 = município; objeto abaixo; nunca um id como título |
| `panel/funding/[id]` (faixa) | empenho na grade secundária | `Empenhado` como 3º valor-herói, com "a utilizar" de apoio |
| `panel/funding/[id]` (dados) | campo "Município (IBGE)" só com o código | "Município" nomeado + "Código IBGE" separado; ids ao fim |
| `panel/funding/[id]` (header) | nº da proposta rebaixado junto do UUID; sem data e sem órgão | "Proposta 14275/2026 · criada em 26/03/2026" + órgão, no cabeçalho |
| `ingestion/normalizer` | só chave minúscula casava: `NR_PROPOSTA`/`DIA_PROPOSTA`/`DESC_ORGAO` chegavam vazios | `_ci()` dá alias de caixa; nº, data e órgão do SIconv entram |
| `panel/funding` (lista) | título caindo para `id_externo`; município caindo para o código | objeto ou "sem título na fonte"; município nomeado + IBGE de apoio |
| `panel/my-proposals` | idem | idem |
| `panel/compliance` | `numero` do item na frente da descrição | descrição na frente, `item N` de apoio |
| `panel/works` | obra sem município | município no item quando o território tem mais de um |
| `panel/alerts` | `municipio_nome \|\| municipio_ibge` cru | `municipioPrincipal()` (código rotulado) |
| `services/pdf.py` | abria pelo título; "Município (IBGE)" na 5ª linha | município no topo; empenho/execução; "Identificação" no fim |
| `dispatch_alerts` (WhatsApp) | "proposta {uuid}" | "🔔 São Paulo/SP · UBS — status" |
| `rag.montar_contexto` | `[fonte/id]` na frente, município cru | município nomeado abre a linha; id da fonte fecha |
| `ai/resumo` (curadoria) | "Município (IBGE): 3550308" | `rotulo()` + instrução de citar pelo nome |

Fonte de dados **nunca** vira identidade de registro na UI (seção 19) — e código
de município **nunca** vira nome.

### 35b. As variáveis-fonte da referência da proposta (decisão travada)

O SIconv publica a referência da proposta em colunas PRÓPRIAS, e são elas — não
retaguardas inferidas — que mandam. Quando o dado sai errado na tela, é aqui que
se confere antes de suspeitar de qualquer outra coisa:

| Variável da fonte | Para onde vai | Quem usa |
|---|---|---|
| `NR_PROPOSTA` | `propostas.numero_proposta` | nº no cabeçalho do detalhe, da lista e do PDF |
| `DIA_PROP` + `MES_PROP` + `ANO_PROP` | `propostas.data_proposta` (remontada) | "criada em" no cabeçalho |
| `ANO_PROP` | `services/propostas.ano_de` | **filtro/faceta de ano** e o card "Ano da proposta" |
| `MES_PROP` | `services/propostas.mes_de` | filtro/faceta de mês |

- **`NR_PROPOSTA` vence** os demais candidatos de `numero_proposta` no
  normalizador (é o nº que o gestor digita no portal para conferir).
- **A data de criação é remontada dos TRÊS componentes** (`_data_de_componentes`)
  e vence qualquer coluna única de data: as retaguardas (`data_inicio_vigencia`,
  `data_cadastro`) marcavam a proposta com data que não é a dela.
- **`ano_de`/`mes_de` leem `ANO_PROP`/`MES_PROP` direto do registro-fonte**
  (`dados_fonte`, em qualquer nível/caixa — no CSV eles vivem em
  `plano_acao.csv`). Isso corrige o dado JÁ ingerido no cache sem esperar
  re-sync. Só depois vêm `data_proposta` → sufixo do nº → exercício da execução.
- `mes_de` passou a acompanhar o ano no MESMO referencial (mês de criação);
  prazo final e atualização na fonte viraram retaguarda.
- No connector do CSV o casamento dessas colunas é **exato** (`_col_exata`), não
  por substring: `dia_prop` pescaria também `DIA_PROPOSTA`, e a palavra-chave
  "orgao" pescava `COD_ORGAO_SUP` (código) no lugar do ministério por extenso.

**O prazo de vencimento saiu do cabeçalho** (detalhe e PDF): vinha marcado
errado com frequência — o fim de vigência não é prazo de proposta — e o lugar
dele é o card "Prazos", conferível item a item. No lugar entrou o **ano da
proposta**, exposto pela API como o computado `PropostaRead.ano` (o front não
recalcula safra). A coluna "Prazo" da LISTA de captação segue como está.

## 36. Pareceres do plano de trabalho (consulta pelo nº do plano)

Na fonte, o parecer **não é emitido sobre a proposta**: é emitido sobre o
**plano de trabalho** dela, e a mesma proposta acumula vários ao longo da
análise (concedente e convenente, em datas diferentes, com o link "Visualizar
Parecer"). Logo é 1-N e a chave de consulta é o NÚMERO DO PLANO DE TRABALHO —
que é o que o gestor tem em mãos. Entidade própria, não coluna.

- **Elo** — `propostas.numero_plano_trabalho` (migration `a3c4d5e6f7b8`),
  mapeado no normalizador a partir de `numero_plano_trabalho`/`nr_plano_trabalho`/
  `id_plano_trabalho`/`cd_plano_trabalho`/`numero_plano_acao`/`id_plano_acao`.
  Entra no hash e no `_UPSERT_FIELDS`.
- **Tabela `pareceres`**: `fonte, id_externo, numero_plano_trabalho,
  numero_proposta, municipio_ibge, data_parecer, esfera (concedente|convenente),
  responsavel, papel, cargo, situacao (o VEREDITO: Aprovar/Reprovar/Solicitar
  Complementação/Não se aplica), situacao_analise (Concluída|Em elaboração),
  situacao_planejamento, orgao_analise, codigo_siorg_orgao, valor_reprovado,
  texto, url_parecer, detalhe/proveniencia jsonb, hash_conteudo,
  cache_atualizado_em`. `unique(fonte, id_externo)`.
  Cache global, RLS só-SELECT por município como os demais eixos — com uma
  diferença: `municipio_ibge IS NULL` também é visível, senão a consulta por
  número de plano (sem município resolvido) devolveria vazio.
- **Identidade**: a API dá id próprio (`id_plano_trabalho_analise_pt`) e é ele
  que manda — convertido para string, porque a rota devolve INTEIRO e o schema é
  texto. A chave sintética (`plano|data|responsável|papel`) só entra quando a
  linha vem do SCRAPING, que não tem id; com o papel na composição, as linhas
  repetidas por papel (que a tela emite) não colidem.
- **Hash LOCAL** (`ingestion/normalizer_parecer.py`): `compute_hash` de
  `normalizer.py` filtra pelos campos da PROPOSTA — reusá-lo aqui daria o mesmo
  hash para todo parecer e nenhuma mudança seria detectada. Mesma disciplina de
  `normalizer_obra`.
- **Connector** `connectors/pareceres.py` — o ÚNICO que coleta por plano de
  trabalho em vez de município (não implementa o Protocol de `base.py`).
  **Existem DUAS APIs do módulo especiais e os dialetos são diferentes** — a
  rota é resolvida pelo spec (`_especiais.descobrir`), nunca chutada:
  (a) **nova** `api-publica.../especiais/` (OpenAPI 3.1/FastAPI) —
  `planos_trabalho_analises_especiais` (PLURAL), filtro direto
  (`id_plano_trabalho=123`), paginação `pagina`/`tamanho_da_pagina`, resposta em
  envelope `{data, total_pages, total_items, page_number, page_size}`. É o
  padrão. (b) **antiga** `api.../transferenciasespeciais/` (PostgREST) —
  `plano_trabalho_analise_especial` (SINGULAR), filtro `eq.123`, paginação
  `limit`/`offset`, lista pura. Mandar o dialeto errado no PostgREST não dá 404:
  o filtro é IGNORADO e voltam as análises do país inteiro — parecer de outra
  proposta na tela. A chave é o **id INTEIRO** do plano; `id_do_plano()` barra o
  que não for numérico (mandar "14275/2026" daria 422 e o gestor leria "fonte
  indisponível" onde a verdade é "não tenho o id") —
  `connectors/planos_trabalho.py` resolve esse id a partir da proposta.
  Colunas da API nova: `id_plano_trabalho_analise_pt` (identidade),
  `situacao_parecer_analise_pt` (veredito: Aprovar/Reprovar/Solicitar
  Complementação/Não se aplica), `situacao_analise_pt` (Concluída/Em
  elaboração), `situacao_planejamento_pt`, `data_analise_pt`,
  `texto_parecer_analise_pt`, `valor_reprovado_pt`, `nome_orgao_analise_pt`,
  `codigo_siorg_orgao_analise_pt`, `id_plano_trabalho`. A API **não** traz
  responsável/papel/cargo — por isso o scraping da tela de tramitação segue como
  2ª fonte: a API dá o veredito e o texto, a tela dá QUEM assinou. (Há ainda
  `/plano_trabalho_analise_historico_especiais` para o histórico das análises,
  com `responsaveis_analise_pt_hist` — caminho para trazer o responsável sem
  scraping.)
- **Serviço** `services/pareceres.py`: cache-first (TTL 12h), `por_plano` (a
  consulta direta) e `por_proposta` (resolve o plano e delega; sem nº de plano,
  tenta o nº da proposta). Falha de fonte → `sync_runs` + status na resposta.
- **Endpoints**: `GET /opinions?work_plan=14275/2026` e
  `GET /proposals/{id}/opinions`, ambos com `?atualizar=true` para forçar coleta.
- **Web**: `components/PareceresSecao.tsx` no detalhe da proposta — mostra o nº
  do plano no cabeçalho (é o que se confere na fonte) e distingue os três
  estados que não podem virar a mesma tela vazia: **sem plano de trabalho** ·
  **fonte não consultável** · **plano sem parecer**.

A rota da API está calibrada pelo spec oficial; **a URL da tela de tramitação
(scraping) segue por calibrar** — `pareceres_url_tramitacao` nasce vazia e, sem
ela, o scraping é pulado sem virar erro. O connector nunca devolve vazio como se
não houvesse parecer: falha de fonte vira mensagem explícita em `sync_runs` e na
tela.

## 37. Class — help desk interno + módulos de aulas + hints contextuais (ⓘ)

O gestor tem dúvida de VOCABULÁRIO ("o que é um empenho?") no momento em que o
dado aparece na tela. O **Class** (nome de produto do help desk interno)
responde isso com TRÊS portas para o mesmo conteúdo: a página do Class, o link
compartilhável e — o diferencial — o **hint contextual**: um ícone ⓘ ao lado
do próprio elemento (ex.: a variável "Empenhado" no detalhe da proposta) que
abre popover com resumo, o primeiro vídeo do artigo e o link para o conteúdo
completo. Além dos artigos avulsos, o Class tem **módulos de aprendizagem**:
trilhas que ordenam AULAS (aula = artigo com `modulo_id` — MESMO motor de
corpo/mídias/hints/link; `ordem` é a posição na sequência).

- **Tabelas** (migrations `d4e5f6a7b8c9` + `e5f6a7b8c9d0`, nível-plataforma sem
  RLS, como `base_conhecimento`; só admin escreve): `helpdesk_categorias` ·
  `helpdesk_modulos` (titulo, slug, descricao, publicado, ordem) ·
  `helpdesk_artigos` (corpo em markdown leve, `slug` único = link compartilhável
  `/panel/class/<slug>`, `publicado`, `modulo_id` FK **SET NULL** — excluir
  módulo devolve as aulas ao acervo avulso) · `helpdesk_midias` (vídeo por URL
  YouTube/Vimeo/mp4 OU arquivo em bytea `conteudo` — container efêmero, disco
  não é storage; teto 50MB, vídeo maior vai por URL; `orientacao`
  horizontal|vertical) · `helpdesk_hints` (`chave` única do elemento de UI →
  artigo, `ativo`).
- **Catálogo de chaves** — `services/helpdesk.py::HINT_CHAVES` é a fonte de
  verdade das chaves plantáveis (`proposta.empenhado`, `proposta.prazo`,
  `funding.tipo`…), com rótulo e tela p/ o admin escolher. Ponto novo de hint =
  entrada no catálogo + `<Hint chave="..."/>` na tela. O PUT de hint valida a
  chave contra o catálogo.
- **Endpoints usuário** (`/class/*`, módulo de plataforma `ajuda` da §29 — a
  CHAVE interna segue `ajuda`, o label é "Class"; desligado → 404 e o front não
  desenha ícone): `GET /class/categories` · `GET /class/modules` (publicados,
  contagem de aulas publicadas) · `GET /class/modules/{slug}` (aulas em
  sequência — é daqui que a aula tira anterior/próxima) ·
  `GET /class/articles?q=&categoria=` (sem busca só artigos AVULSOS — aula vive
  no módulo; com `q` as aulas entram no resultado) · `GET /class/articles/{slug}`
  (serve artigo E aula) · `GET /class/hints` · `GET /class/media/{id}` (arquivo
  autenticado — o front busca com Bearer e toca via object URL).
- **Endpoints admin** (`/admin/class/*`, superuser): CRUD de categorias,
  módulos (`GET/POST /admin/class/modules` · `GET/PATCH/DELETE .../{id}` — o GET
  devolve TODAS as aulas, inclusive rascunhos) e artigos (create/PATCH aceitam
  `modulo_id` + `ordem` = virar aula; PATCH de título regenera o slug; DELETE
  cascateia mídias/hints), mídia por URL (`POST .../media`) e upload multipart
  (`POST .../media/upload`), `GET /admin/class/hint-keys` ·
  `GET/PUT /admin/class/hints` (upsert por chave — realocar transfere o ícone) ·
  `DELETE /admin/class/hints/{chave}`.
- **Corpo em RICH TEXT (TipTap) + player Plyr**: o corpo do artigo/aula é HTML
  do editor TipTap (`components/RichTextEditor.tsx` — títulos/negrito/listas/
  citação/link e o nó `components/editor/VideoEmbed.tsx`, que EMBEDA vídeo no
  meio do texto e serializa como `div[data-video][data-orientacao]`). A
  renderização é `components/CorpoConteudo.tsx`: sanitiza com DOMPurify
  (allowlist estrita; único `dangerouslySetInnerHTML` do app) e troca os
  marcadores pelo player. Corpo LEGADO em markdown leve continua renderizando
  pelo caminho antigo e é convertido (`markdownLeveParaHtml`) ao abrir no
  editor. O player é o **Plyr** (`components/HelpVideo.tsx`): YouTube/Vimeo
  pelo provider de embed nativo, arquivo mp4/upload no html5 (com
  **picture-in-picture**), **Bunny Stream** (`iframe.mediadelivery.net`) e
  `/embed/` desconhecidos caem no iframe do provedor. ATENÇÃO estrutural: o
  Plyr embrulha/move o alvo no DOM — o React só é dono do HOLDER; o elemento
  de mídia é criado imperativamente no effect (senão a desmontagem quebra).
  CSS: `.rich-text` (tipografia igual no editor e na página = WYSIWYG),
  `--plyr-color-main` no lime; `plyr.css` importado no layout raiz.
- **Web usuário**: `lib/help.tsx` (`HelpProvider` no layout do painel carrega o
  mapa de hints UMA vez; degrada silencioso sem módulo/sem rede;
  `analisarVideo` decide o modo do player) e `components/Hint.tsx` (ⓘ +
  popover; busca o artigo só na 1ª abertura). Com PiP ativo, clique fora NÃO
  fecha o popover (fecharia o vídeo). Páginas `app/panel/class` (módulos +
  busca + chips de categoria), `app/panel/class/modules/[slug]` (trilha de
  aulas) e `app/panel/class/[slug]` (artigo/aula; aula mostra "aula N de M" +
  anterior/próxima via `/class/modules/{slug}`). Item "Class" no menu
  profile-centric.
- **Web admin**: `app/admin/class` (criar artigo → editor; módulos com
  publicar/excluir inline; categorias) e `app/admin/class/[id]` (conteúdo em
  rich text + publicar/despublicar, seletor de módulo + posição — transforma
  artigo em aula —, mídias com orientação, e a seção Hints: escolhe a chave no
  catálogo agrupado por tela, vê se a chave já pertence a outro artigo,
  pausa/remove). Publicação é o interruptor em DOIS níveis: módulo rascunho
  não lista (aulas publicadas seguem acessáveis por link/busca); aula rascunho
  não abre.
- **Hints plantados hoje**: detalhe da proposta (valor total, contrapartida,
  empenhado, prazo, situação, pendências, modalidade, nº da proposta, execução
  financeira) e captação (chips cadastrada×disponível). `Dado` de `ui.tsx`
  aceita `rotulo: ReactNode` para acomodar o ⓘ.

## 38. Desempenho — a busca ao vivo não pode parar o painel (decisão travada)

A lentidão generalizada (painel, central de ajuda, admin) não vinha das telas:
vinha da busca ao vivo monopolizando o processo da API (uvicorn de 1 worker).
Três causas, três correções — e a regra que fica: **coleta é I/O externo; não
bloqueia o event loop, não segura conexão de banco e não se repete sem TTL.**

- **Event loop bloqueado**: o parse do CSV nacional do `transferegov_disc`
  (~1 GB descomprimido) rodava síncrono no event loop — enquanto varria o
  arquivo, a API INTEIRA parava (qualquer rota, qualquer usuário). Agora roda
  em thread (`asyncio.to_thread`), com cache do RESULTADO por (url, município)
  no mesmo TTL de 1h dos bytes, e lock de download (N buscas simultâneas não
  baixam N × 200MB). Connector novo com parse pesado segue o mesmo padrão.
- **Coleta sem memória de "não achei nada"**: o frescor do cache-first era
  julgado pela EXISTÊNCIA de linhas frescas — município sem registro numa fonte
  refazia a coleta inteira (CSV, Chromium) em TODA carga do painel.
  `services/consulta_avulsa` ganhou cache de TENTATIVA em memória por
  (fonte, município): sucesso vale `cache_ttl_seconds` (6h), falha vale
  `coleta_erro_ttl_seconds` (10 min). Cada coleta tem teto
  `coleta_timeout_seconds` (5 min) — fonte pendurada não segura o request.
  `limpar_cache_coleta()` zera (conftest limpa por teste, junto do TRUNCATE).
- **Fontes em série segurando a sessão RLS**: o `live_search` chamava fonte
  atrás de fonte dentro da transação do request (conexão presa por minutos →
  pool esgotado → até o `/users/me` do guard de admin esperava vaga). Agora o
  fluxo é: (1) sob a sessão, decidir o que precisa coletar; (2) coletas em
  PARALELO (semáforo de 3 — Chromium/CSV disputam CPU) sem tocar o banco;
  (3) ingestão sequencial + `sync_runs` + status. O pool subiu para
  `db_pool_size=10`/`db_max_overflow=20` (cada request segura até 2 conexões:
  auth + RLS).
- **Guard de módulos cacheado**: `require_modulo` abria sessão de banco em toda
  request de router guardado. `esta_ativo` agora usa snapshot em memória com
  TTL 10s, invalidado por `definir()` (toggle do painel propaga em segundos);
  banco fora do ar degrada para os `padrao` do registro em vez de 500.
- **Latência instrumentada**: `core/latencia.py` (middleware ASGI puro — não
  embrulha corpo, não interfere no SSE) carimba `X-Response-Time` em todo
  response e loga WARN para request acima de `log_request_lenta_ms` (1s) com
  rota, status, duração e estado do pool. "Está lento" em produção vira uma
  linha de `docker logs` apontando a rota culpada — investigar lentidão começa
  por aí, não por reproduzir.

## 39. Gates de features por PLANO (config do plano)

Complemento da §29: além do liga/desliga de módulos da PLATAFORMA, cada **plano**
(`planos.limites`, jsonb) carrega a CONFIG do que a assinatura inclui —
liberação plano a plano, editável no painel admin sem redeploy. A fonte de
verdade da leitura é `services/plano_gates.py` (normaliza o jsonb, aceita as
chaves legadas `municipios`/bool-de-módulo no topo, cacheia por plano TTL 10s).

Formato canônico de `planos.limites` (chave AUSENTE = sem restrição):
`{"municipios_max": 5, "membros_max": 2, "modulos": ["captacao", ...],
"fontes": ["transferegov"], "features": {"export_pdf": false}}` —
`fontes` aceita grupo OU connector id (grupo expande); `features` conhecidas em
`plano_gates.FEATURES` (export_pdf, relatorio_csv, alertas_email, alertas_wpp;
ausente = liberada). Validação tipada em `schemas/planos.py::PlanoLimites`
(módulo/fonte desconhecidos = 422). Usuário SEM plano → sem restrição;
superuser nunca é limitado por plano.

- **Guard em duas camadas** — `require_modulo` (agora com usuário OPCIONAL via
  `core/users.current_user_optional`): plataforma desligada → 404
  `MODULO_DESATIVADO`; módulo fora do plano do usuário → **403
  `MODULO_NAO_INCLUIDO_PLANO`** (o front distingue e oferece upgrade em vez de
  sumir a tela — `components/ModuloGate.tsx`). Módulo novo **`alertas`**
  (padrao on) guarda os routers de alertas e monitoramentos; o item do menu e a
  página `panel/alerts` acompanham.
- **Perfil** — `GET /profile` devolve `modulos` EFETIVOS (plataforma ∩ plano) e
  `plano` (nome/slug, municipios_max, membros_max, features efetivas, grupos de
  fonte e módulos do plano). Menu, ModuloGate e Dynamic Island (copiloto) leem
  daí; `profile/overview` não consulta dimensão fora do plano.
- **Fontes por plano** — onboarding (`services/onboarding`), live-search
  (`consulta_avulsa`) e 1º sync (`primeiro_sync`) filtram por
  `plano_gates.filtrar_fontes`; o chat de onboarding só oferece os grupos do
  plano (`perfil.plano.fontes`). Fonte fora do plano não é coletada nem entra
  no status.
- **Limites** — `municipios_max` segue no onboarding (403
  `LIMITE_PLANO_MUNICIPIOS`); **membros da conta**: o usuário convida a própria
  equipe em `GET/POST /account/members(/invites)` + DELETE (revogar pendente) —
  o convite herda o plano do convidante, papel default equipe, aceite pelo
  `/auth/accept-invite` de sempre; `membros_max` conta convites vivos
  (pendentes+aceitos) → 403 `LIMITE_PLANO_MEMBROS`. UI em `panel/account`.
- **Features** — PDF (`/proposals/{id}/pdf`) e CSVs (captação/emendas) checam
  `plano_gates.exigir_feature` → 403 `FEATURE_NAO_INCLUIDA_PLANO`; os canais
  email/wpp da varredura de alertas são descartados quando a feature está off
  (o alerta segue no painel).
- **Admin** — `GET /plans/options` (catálogos de módulos/fontes/features p/ o
  editor), `GET /plans?incluir_inativos=true` (só admin), editor completo em
  `app/admin/plans` (chips de módulos/fontes, limites numéricos, toggles de
  features; "todos marcados" grava sem a chave = sem restrição). Criar/editar
  plano invalida o cache (`plano_gates.limpar_cache`). Seeds de
  `core/bootstrap.PLANOS_PADRAO` já no formato canônico.

## 40. Meu painel independente dos módulos de exploração (decisão travada)

Desligar o módulo `captacao` APAGAVA o dashboard: o gate cobria o router de
`proposals` inteiro (inclusive o `/proposals/summary` do Panorama financeiro) e a
visão geral pulava a dimensão — com recebidos/conformidade/obras desligados por
padrão, o `/panel` ficava vazio. A regra que fica:

- **Módulo = EXPLORAÇÃO do eixo, não o dado.** `captacao` liga/desliga os filtros
  específicos (lista/facetas/relatório), a **consulta ATIVA nas fontes**
  (`POST /proposals/live-search`, além do que o onboarding preencheu) e os
  pareceres (coleta ao vivo). As leituras de CACHE do território são panel-core e
  ficam FORA do gate: `GET /proposals/summary`, `/proposals/deadlines`,
  `/proposals/{id}` e `/proposals/{id}/pdf` (gate por endpoint em
  `api/v1/propostas.py`; regressão em
  `test_modulos.py::test_gate_captacao_so_na_exploracao`).
- **Visão geral data-driven** (`services/perfil.visao_geral`): a dimensão entra se
  o módulo está ativo OU se há dado no cache do território; módulo desligado →
  `href=None` (`DimensaoResumo.href` agora é opcional) e o card do painel vira
  informativo, sem navegação. Desligado E sem dado → fora da visão.
- **Web**: o Meu painel NÃO faz live-search (removido o fetch morto de
  oportunidades — coleta ativa é papel da Captação); "Minhas Propostas"
  (favoritas = acompanhamento do cache) saiu do módulo captação no menu; a página
  Captação ganhou `ModuloGate`; o detalhe da proposta é panel-core e, sem o
  módulo, esconde apenas a seção de pareceres.

## 41. Zeragem — admin (global) e usuário (zona de perigo da conta)

Duas zeragens com ALCANCES diferentes, porque `propostas` (e `repasses`,
`conformidades`, `obras`) é **cache global** (§4) e não pertence a um usuário.

- **SOFT DELETE (`propostas.excluido_em`, migration `f6a7b8c9d0e1`)**: zerar
  MARCA, não apaga. As FKs são `ON DELETE CASCADE` e **cascade ignora RLS**, então
  um DELETE levava junto favoritos, pastas, monitoramentos e alertas de QUALQUER
  usuário do município. Marcada, a linha some do painel, a curadoria de todos
  sobrevive e dá para desfazer (`POST /admin/proposals/restore`).
- **O filtro mora na CONSULTA, não na policy de RLS** (`excluido_em IS NULL` em
  `propostas._condicoes`/`obter`/`listar_por_prazo`, `consulta_avulsa._cache_fresco`,
  `favoritos`, `oportunidades`, `perfil`, `rag`, jobs de curadoria/embed).
  Tentador era pôr na policy de SELECT — mas `INSERT ... ON CONFLICT DO UPDATE`
  valida a linha EXISTENTE contra o RLS: escondida ali, a coleta quebraria com
  violação de RLS em vez de RESSUSCITAR a proposta (o upsert zera `excluido_em`,
  porque a fonte ainda a publica).
- **Admin — `DELETE /admin/proposals`** (`api/v1/admin_fontes.py`, superuser):
  marca TODAS as propostas. O UPDATE vai **sem WHERE** de propósito: a sessão é a
  de plataforma (sem tenant) e, sob o `FORCE RLS` de `propostas`, qualquer
  LEITURA enxerga 0 linhas — com WHERE o comando lê linha, cai na policy de
  SELECT e marcaria zero. Pelo mesmo motivo a contagem sai do **`rowcount`**,
  nunca de um `SELECT count(*)` (o painel respondia "0 removidas" com a tabela
  inteira zerada).
- **Usuário — `DELETE /profile`** (`services/perfil.py::zerar`, zona de perigo
  em `app/panel/account`): devolve a conta ao estado **pré-onboarding**. Apaga
  o que é do tenant — território (todos os municípios), preferências
  (áreas/fontes) e curadoria (favoritos, pastas, monitoramentos, buscas
  monitoradas, alertas). **Não** apaga conta, login nem agenda de contatos, e
  registra `audit_log('zerar_perfil')`.
- **Zeragem por usuário**: as propostas do território levam soft delete e os
  demais caches (repasses/conformidades/obras) perdem o `cache_atualizado_em`.
  Nada é apagado — outro tenant pode acompanhar o mesmo município e o cascade
  destruiria a curadoria dele. O app-role NÃO consegue detectar "esse município é
  só meu": `FORCE RLS` em `municipios_interesse` bloqueia leitura cross-tenant
  até para a sessão de plataforma; por isso a regra é marcar, nunca apagar.
- **ORDEM IMPORTA**: o cache é zerado ENQUANTO o território ainda existe. O
  UPDATE tem WHERE, logo LÊ linha — e leitura em `propostas` passa pela policy
  de SELECT (município ∈ `municipios_interesse`). Apagando o território antes, o
  UPDATE não acha nada e o cache fica fresco para sempre.
- **Memória de coleta**: as duas zeragens limpam o cache de TENTATIVA de
  `consulta_avulsa` (`limpar_cache_coleta()` no admin, `esquecer_municipio(ibge)`
  por município no usuário) e o admin limpa também o CSV do `transferegov_disc`.
  Sem isso, "recomeçar do zero" não recoletaria nada por até 6h (§38) e o painel
  novo abriria vazio como se as fontes não tivessem dados.

## 42. Enriquecimento da proposta — emenda, parlamentar autor e TIMELINE de andamento

A proposta deixou de ser uma ficha estática: além dos pareceres (§36), o detalhe
agora responde **de quem é o dinheiro** (emenda + parlamentar autor) e **em que pé
está** (linha do tempo da tramitação). Os dois vêm de rotas IRMÃS do módulo
`especiais`, consultadas pelas chaves da PROPOSTA — não por município.

- **Rota descoberta, não chutada** (`connectors/_especiais.py`): o spec do módulo
  (`<base>/openapi.json` — o que a página `/docs` consome) é lido em runtime e a
  rota só é aceita com DUAS evidências: o nome casa o assunto ("emenda") **e** ela
  aceita uma das nossas chaves (`id_plano_acao` > `numero_plano_acao` >
  `id_plano_trabalho` > `numero_proposta`). A segunda evidência é a que protege o
  gestor: rota do assunto sem filtro devolveria o Brasil inteiro paginado como se
  fosse a emenda dele. Cobre os dois dialetos do TransfereGov — OpenAPI 3
  (`?id_plano_acao=123`, `pagina`/`tamanho_da_pagina`) e PostgREST/Swagger 2
  (`?id_plano_acao=eq.123`, `limit`/`offset`). Overrides no painel:
  `especiais_base_url`, `emendas_esp_endpoint`, `emendas_esp_chave`.
- **Entidade `proposta_emendas`** (migration `f3a4b5c6d7e8`): 1-N com a proposta
  (um plano de ação pode somar emendas de autores diferentes), com `codigo/numero`,
  `ano`, `tipo_emenda`, **autor** (`parlamentar`, `partido`, `uf_parlamentar`,
  `cargo`, `codigo`) e valores (`valor`, `valor_empenhado`, `valor_pago`).
  `unique(fonte, id_externo)`; cache global com RLS só-SELECT por município (nulo
  visível, como `pareceres`). NÃO confundir com a lente de emendas dos repasses
  (§26b): lá é dinheiro que já caiu; aqui é a origem da captação.
- **De-para por PALAVRA, não por substring** (`ingestion/normalizer_emenda.py`): as
  colunas vêm com o sufixo da entidade (`nome_parlamentar_emenda_plano_acao`), então
  o casamento é por conjunto de palavras da coluna. Casar por substring é armadilha
  — "ano" está dentro de "pl**ano**", e `id_emenda_plano_acao=90871` virava o ano
  9087 da emenda (regressão em `test_andamento.py`). `codigo_parlamentar` é excluído
  do candidato a NOME do autor. Hash local sobre os campos materiais (empenho novo →
  mudança detectada).
- **Degradação com conteúdo** (`services/emendas_proposta.py`): sem rota calibrada
  ou com a fonte fora do ar, a emenda ainda sai do **registro-fonte** que o plano de
  ação já traz (`emendas_do_registro_fonte` — parlamentar + valor do repasse, sem
  rede). `coleta.origem` (`fonte` | `registro_fonte` | `cache`) e `coleta.erro` vão
  na resposta: "não consegui consultar" nunca vira "não tem emenda".
- **Timeline** (`services/andamento.py` + `schemas/andamento.py`): pareceres +
  marcos da proposta (cadastro na fonte, assinatura, início/fim de vigência, prazos,
  pendências, movimentação datada) viram `EventoAndamento`
  (`data/tipo/titulo/detalhe/ator/tom/valor/texto/url/futuro`), ordenados do mais
  recente para o mais antigo, sem data por último. `futuro` separa histórico de
  compromisso a vencer; o tom do prazo usa a mesma escada de `lib/format.ts::tomPrazo`.
  **Fato sem data não entra**: datar por chute (o ano da emenda virando 1º de
  janeiro) produziria cronologia verossímil e errada — por isso a emenda tem seção
  própria em vez de virar evento. Parecer "Aprovar" ainda **em elaboração** não é
  decisão: sai com tom neutro.
- **Endpoints** (`api/v1/andamento.py`): `GET /proposals/{id}/timeline` e
  `GET /proposals/{id}/amendments`, ambos com `?atualizar=true`. Gate por ENDPOINT
  e não por router (§40): ler do cache é panel-core — desligar `captacao` não pode
  apagar o andamento do detalhe; o que o módulo governa é a consulta ATIVA, então
  `atualizar=true` é ignorado com o módulo desligado.
- **Web**: `components/AndamentoProposta.tsx` (linha do tempo com trilho, dot por
  tom, veredito em badge e texto do parecer expansível) e
  `components/EmendasProposta.tsx` (autor lidera — é com o gabinete dele que o
  gestor fala; a seção some quando a proposta simplesmente não é de emenda).
  Ambos no detalhe (`app/panel/funding/[id]`), substituindo `PareceresSecao.tsx`
  (removido — o conteúdo foi absorvido pela timeline). Incidente de fonte virou
  AVISO no topo, não substituto da lista: o que está no cache continua na tela.
- **Calibração** — `python -m src.tools.probe_especiais --rotas` lista as rotas do
  módulo que falam do assunto e os parâmetros de cada uma (é daí que sai o valor dos
  overrides); `--id-plano-acao <id>` bate na rota e mostra campos brutos +
  normalizados. Precisa de saída para gov.br (o sandbox de CI/agente bloqueia).

## 43. Ordem do painel — "recentes" é a data da PROPOSTA

A lista da Captação ordenava por `cache_atualizado_em`, que é quando NÓS
coletamos: uma proposta de 2019 recoletada hoje aparecia na frente de uma criada
este mês. A referência agora é `data_proposta` — a data de CRIAÇÃO na fonte,
remontada de **DIA_PROP + MES_PROP + ANO_PROP** (as variáveis oficiais do SIconv,
em `ingestion/normalizer._data_de_componentes`), que já vencem qualquer candidato
de coluna única.

- `services/propostas._ORDEM_SQL` = `data_proposta DESC NULLS LAST`,
  `cache_atualizado_em DESC` (desempate) e `id` (desempate ESTÁVEL — sem ele o
  LIMIT/OFFSET repete e pula linhas entre páginas). Ordenar por coluna mantém o
  caminho rápido de paginação no SQL.
- Proposta sem data de criação na fonte não some da lista: vai para o fim
  (`nullslast`) e se ordena pela coleta entre as iguais.
- Migration `a7b8c9d0e1f2` faz o **backfill** de `data_proposta` a partir dos três
  componentes já guardados em `dados_fonte` (o CSV do SIconv manda em CAIXA ALTA;
  daí o COALESCE das duas caixas). Sem isso, tudo que foi ingerido antes ficaria
  no fim da lista até a próxima recoleta. Usa `to_date` e não `make_date`: um
  registro sujo que passe pelos guardas não pode derrubar a migration.

## 43. Empenho da proposta — `/empenhos_especiais` (o recurso saiu do papel?)

O empenho não aparecia no painel, e a causa não era a tela: `execucao.
valor_empenhado` (§28) só existe quando o painel da Visão Geral publica o
AGREGADO, e no módulo especiais o empenho mora em rota própria —
`/empenhos_especiais`, consultada pelo **número da proposta**. Faltava coletar.

- **Entidade `proposta_empenhos`** (migration `b8c9d0e1f2a3`): 1-N (a proposta
  acumula ordinário, reforço, anulação), com `numero_empenho`, `data_empenho`,
  `tipo`, `situacao`, os valores (`empenhado`/`anulado`/`liquidado`/`pago`) e a
  origem do recurso (UG emitente, gestão, natureza de despesa, fonte, programa
  de trabalho). Cache global com RLS só-SELECT por município, como `pareceres`.
- **Refiltro no cliente, SEMPRE** (`connectors/empenhos_especiais.py`): a rota é
  conhecida, mas o nome do parâmetro de filtro não — e **FastAPI ignora query
  param desconhecido** em vez de recusar. Mandar `numero_proposta` numa rota que
  espera outro nome devolveria a tabela NACIONAL paginada, e o gestor veria
  empenho alheio como se fosse dele. Então toda linha é conferida contra o
  número da proposta (comparação só-dígitos: "14275/2026" casa "142752026").
  Linha que não casa é descartada; resposta que não ecoa NENHUMA coluna de
  identificação só é aceita quando o spec confirmou o filtro (`Rota.confirmada`).
- **Anulação não é recurso disponível** (`ingestion/normalizer_empenho.py`):
  `valor_anulado_*` casa "valor" e seria lido como empenhado — `_NAO_EMPENHADO`
  exclui anulado/cancelado/estorno do candidato. No total
  (`services/empenhos_proposta.resumir`) o empenhado sai **líquido** das
  anulações, e nunca negativo.
- **Totais na faixa de destaque**: `EmpenhoResumo` (empenhado, anulado,
  liquidado, pago, **a utilizar** = empenhado − pago, primeiro/último empenho). O
  detalhe usa o agregado da `execucao` quando existe e **cai para a soma dos
  documentos** quando não — que era o caso em que a faixa aparecia vazia.
- **Timeline**: cada empenho datado vira evento (§42). Empenho anulado por
  inteiro sai `danger`, anulado em parte `warn`, emitido `ok` — pintar os três de
  verde diria que há recurso reservado onde ele foi devolvido. A timeline LÊ o
  cache (quem coleta é `/commitments`), senão a mesma tela dispararia duas
  coletas concorrentes da mesma coisa.
- **Endpoint**: `GET /proposals/{id}/commitments?atualizar=` (§25: empenhos →
  commitments), com o mesmo gate por endpoint da §40.
- **De-para compartilhado** (`ingestion/_campos.py`): `palavras`/`por_termos`/
  `decimal_br`/`data_de`/`so_digitos` saíram do normalizador de emenda e agora
  servem os dois — a regra de casar por PALAVRA da coluna (nunca substring) mora
  em um lugar só.
- **Config** (categoria fonte): `empenhos_esp_endpoint` (padrão
  `empenhos_especiais`) e `empenhos_esp_chave` (padrão **`id_plano_acao`**). O
  spec oficial mostra que `/empenhos_especiais` só aceita `id_plano_acao` como
  vínculo com a proposta — `numero_proposta`, que era o padrão, é IGNORADO pelo
  FastAPI e a resposta vinha com os empenhos do país inteiro (valor de empenho
  alheio na proposta). O `id_externo` só serve de retaguarda para `id_plano_acao`
  quando é inteiro: no CSV do SIconv ele é "30011/2026". Campo de valor na rota:
  `valor_empenho`.
- **Calibração**: `python -m src.tools.probe_especiais --rotas` passou a mostrar
  também a rota escolhida para empenho, e `--numero-proposta 14275/2026` bate na
  rota e mostra campos brutos + normalizados.
## 44. O nº da proposta é uma PÍLULA (destaque), não linha de apoio

Complemento operacional da §35: a hierarquia já dizia que a referência da
proposta é dado de CABEÇALHO, mas na prática o número seguia diluído — mesmo
tamanho e mesma cor do órgão e da modalidade, numa linha `text-xs text-ink-3`.
Quem varre a lista atrás de um número tinha que ler todas as linhas de apoio.

- **`components/NumeroProposta.tsx`** é a forma única do número em toda
  superfície de lista: pílula mono com o acento da marca (lime), `Nº` em
  rótulo, `select-all`, e **clique copia** (o passo seguinte do gestor é colar
  no portal da fonte ou no WhatsApp). `termo` realça o trecho pesquisado.
  `copiavel={false}` quando a pílula fica DENTRO de um `<Link>` — botão
  aninhado em âncora é HTML inválido e o clique disputaria com a navegação.
  Sem número, o componente **não renderiza** (nunca cai para `id_externo`: §35).
- **Onde está**: feed do Meu painel (`app/panel/page.tsx`), lista da Captação
  (encabeçando a célula, acima do título), Minhas Propostas e o cabeçalho do
  detalhe. Em Minhas Propostas o `id_externo` SAIU da linha de apoio — era
  plumbing ocupando o lugar da referência.
- **Feed**: `NovidadeItem.numero_proposta` (schemas/perfil) é preenchido em
  `services/perfil.novidades`. Não confundir com `proposta_id` (UUID interno,
  que nunca aparece na tela).
- **Busca pelo número** já existia no backend (`_busca_textual` casa
  `numero_proposta` e `id_externo`); o que faltava era a tela dizer isso — o
  placeholder do campo de busca da Captação abre com "nº da proposta".

**Nº da proposta NUNCA cai para `id_externo`.** O campo "Nº da proposta" de
"Dados gerais" (detalhe e espelho PDF) e a referência do cabeçalho do PDF
tinham retaguarda `p.numero_proposta or p.id_externo`: sem NR_PROPOSTA, o
identificador da INTEGRAÇÃO aparecia rotulado como número da proposta — um
número que o portal da fonte não reconhece e que o gestor levaria para a
conversa com o órgão. Sem número, o campo fica vazio ("—") e o id da fonte
segue no campo próprio ("Identificador na fonte"), logo abaixo.

## 45. Lentes de natureza jurídica — entes municipais × outros

A consulta de propostas por **natureza jurídica** parte de DUAS lentes (decisão de
produto), não da taxonomia inteira: `entes_municipais` (prefeitura, secretaria
municipal, câmara de vereadores, fundo/autarquia/fundação municipal e consórcio
intermunicipal) e `outros` (organizações da sociedade civil, entes estaduais/federais,
empresas). Os 6 slugs detalhados de §31 continuam valendo — a lente os **agrupa**,
não os substitui.

- **Backend** (`services/propostas.py`): `GRUPOS_NATUREZA` (slug → rótulo) e
  `grupo_natureza_de(p)`, que devolve SEMPRE uma das duas lentes — sem natureza
  conhecida a proposta cai em `outros`, então as duas somadas cobrem o recorte
  inteiro e nenhuma proposta fica invisível às duas. `_NATUREZAS_MUNICIPAIS`
  (`municipal` + `consorcio`) é o ponto de calibração do agrupamento.
- **Sinais de reserva da natureza**: `natureza_juridica_de` deixou de depender só de
  `execucao.natureza_juridica`. A ordem é execução → texto no registro-fonte
  (`_CAMPOS_NATUREZA_FONTE` via `_campo_fonte`) → código CONCLA/RFB
  (`_CODIGOS_MUNICIPAIS`/`_CODIGOS_CONSORCIO`) → nome do proponente
  (`_CAMPOS_PROPONENTE`, só quando reconhece um marcador) → `_NATUREZA_PADRAO_FONTE`
  (fundo a fundo repassa ao próprio município). Isso também aumenta a cobertura do
  filtro detalhado, que antes perdia toda proposta sem o campo na execução.
- **API**: `natureza_grupo=entes_municipais|outros` em `FiltrosProposta` — vale para
  `/proposals`, `/proposals/facets`, `/proposals/summary` e o relatório CSV. Entra
  também como dimensão de faceta (`natureza_grupo`), com contagem.
- **Meu painel**: `DimensaoResumo.quebras` (`schemas/perfil.py`) leva recortes de uma
  dimensão para o card; a captação traz a contagem por lente com link já filtrado
  (`/panel/funding?natureza_grupo=…`). Sem navegação (módulo desligado, §40) a quebra
  vem vazia. A contagem é em Python — a natureza é derivada de jsonb/registro-fonte.
- **Web**: `app/panel/funding` mostra as lentes na barra PRINCIPAL ("Quem propõe"),
  não nos filtros avançados, e lê `?natureza_grupo=` na chegada (o card do painel abre
  a tela já filtrada). Os 6 slugs seguem no avançado, para refinar.

## 46. Faixa de destaque do detalhe — EMPENHO é `VL_GLOBAL_PROP`

O card **Empenho** da faixa de destaque da página da proposta mostra o **valor
global que a fonte publica para a proposta** — `VL_GLOBAL_PROP`, a variável
oficial do SIconv (`VL_GLOBAL_CONV` é a do convênio já celebrado).

- **Resolução do valor** (`services/propostas.valor_global_de`): lê
  `VL_GLOBAL_PROP` direto de `dados_fonte`, em qualquer nível e caixa e em
  formato BR — mesma disciplina de `ano_de`/`mes_de`, então **corrige o que já
  está no cache sem esperar re-sync**. Sem a variável, cai em
  `execucao.valor_global` e, por fim, em `valor_total`. A API expõe o resultado
  no campo computado `PropostaRead.valor_global`; o front **não** vasculha
  `dados_fonte`.
- **Ingestão**: `_EXEC_KEYS["valor_global"]` do normalizador aceita
  `vl_global_prop`/`vl_global_conv` além de `vl_global`, para as fontes que
  publicam a coluna sem passar pelo de-para por palavra-chave do connector.
- **"Empenhado a utilizar" foi DESCARTADO** da página da proposta e do espelho
  em PDF (faixa de destaque, seção "Execução financeira" e o card "A utilizar"
  da seção "Empenhos"). Era conta derivada (`empenhado − pago`) que nas
  propostas dava zero e não informava nada. Os agregados de CARTEIRA continuam
  com o card — `/proposals/summary` (`cards.valor_a_utilizar`), a tela de
  captação e o resumo —, onde a conta tem massa e significado.

**A LINHA BRUTA do CSV é retaguarda de todo campo.** Os connectors de CSV fazem
o de-para coluna→campo e guardam a linha original em `plano_acao.csv`
(`transferegov_disc._plano_do_csv`). Quando o de-para não casa uma coluna, o
campo chegava vazio ao painel MESMO com o valor à vista no registro-fonte — foi
o caso do `NR_PROPOSTA` ("34530/2009" no `csv`, proposta exibida como "sem
número na fonte"). `normalizer._com_linha_bruta` põe a linha bruta como camada
de BAIXO do plano (com alias de caixa): o de-para do connector continua vencendo
onde preencheu, e o que ele não achou vem da fonte. Vale para qualquer connector
que embuta a linha em `csv`. A migration `c9d0e1f2a3b4` faz o mesmo com o que já
está no banco — promove `NR_PROPOSTA` (sobrescrevendo candidato errado, §35b),
preenche os demais candidatos só onde está NULL e remonta `data_proposta` nos
níveis que o backfill anterior (`a7b8c9d0e1f2`) não alcançava, porque só olhava a
raiz de `dados_fonte`.

## 47. Filtro de ano do Meu painel — UMA safra para a página inteira (decisão travada)

O `/panel` tinha **dois** filtros de ano com critérios diferentes: o seletor do
panorama pedia a safra à API (gráfico + cards financeiros) e o feed classificava
por conta própria, no cliente, pela data da **coleta**. Filtrar o ano ajustava o
gráfico e deixava os cards das dimensões e as novidades noutro recorte — com
proposta de 2019 listada como novidade do ano corrente.

- **Um seletor só, no cabeçalho da página** (`app/panel/page.tsx`), aplicado a
  `/profile/overview`, `/proposals/summary` e `/profile/feed`. O `PanoramaFinanceiro`
  recebe a safra por prop; não há mais filtro local. A escolha persiste
  (`hub_painel_ano`) e some do seletor safra que não existe mais no território.
- **A safra é sempre a mesma**: `propostas.ano_de` na captação (ANO_PROP >
  `data_proposta` > nº da proposta > exercício) e o ano do pagamento nos
  recebidos (sem data, a competência). O feed passa a expor `NovidadeItem.ano` e
  a `data` da proposta é a **dela** (`data_proposta`), não a da coleta.
- **Filtro no SERVIDOR, antes da janela** (`services/perfil.novidades`): filtrar
  só o que coubesse no `limite` deixava anos anteriores permanentemente vazios.
  A resposta traz `anos: [{ano, total}]` do território INTEIRO (ignora o ano
  escolhido) — senão o filtro apagaria as próprias opções e prenderia o usuário
  na safra escolhida. Ordem do feed: safra decrescente e, dentro dela, a data.
- **Dimensões sem safra**: conformidade e obras são estado ATUAL do município,
  não fluxo anual — continuam inteiras e se anunciam com `recorte_ano=False`; o
  painel avisa em vez de fingir um recorte que não existe.
- O card da captação leva a safra para a exploração
  (`/panel/funding?ano=…&natureza_grupo=…`), e a tela de captação abre já nesse
  recorte.

## 48. Flag de versão da UI — portar a Bancada v2 → v1 pelo painel admin

A modernização visual (Bancada v2: acento duplo lime+aqua, vidro/elevação,
microanimações, aurora/grade no canvas) é a UI atual. A flag permite **voltar
para a v1 clássica em runtime**, sem redeploy e sem remover código — mesma
disciplina dos módulos da §29 e dos gates da §39.

- **Chave** — `ui_versao` no `services/config.py::CATALOGO`, categoria nova
  `plataforma` (aparência/comportamento do app, não credencial). Valores: `v2`
  (padrão, a UI atual) e `v1`. Sem linha no banco vale o padrão.
- **Contrato** — `GET /api/v1/ui` (`api/v1/ui.py`) é **público**: a flag não é
  segredo e precisa valer já no `/login`, antes de existir sessão.
  `versao_ui_efetiva()` sanitiza — valor fora de `{v1, v2}` cai na v2, para
  config inválida nunca quebrar a plataforma.
- **Web** — `components/UiVersionSync.tsx` (montado no layout raiz) consulta a
  rota a cada carga, guarda em `localStorage` (`hub_ui`) e põe `data-ui="v1"` no
  `<html>`; o boot script do `app/layout.tsx` aplica **pré-paint**, como o tema
  claro/escuro (§ toggle) — sem flash. API fora do ar mantém a última versão
  conhecida.
- **CSS** — a camada v1 fica no FIM de `globals.css`, **fora de `@layer`**: estilo
  sem camada vence os de `@layer components`, e `:root[data-ui]` empata em
  especificidade com os blocos de tema (no empate vence a ordem). É a **superfície
  de porte**: acento único lime (gradiente colapsa, aqua some), superfícies flat
  (sem vidro/sombra/fio de gradiente), sem microanimação decorativa e canvas limpo
  (sem aurora/grade). Ajuste fino do porte entra AQUI, nunca nos componentes — as
  duas versões compartilham o mesmo markup.
- **Admin** — `/admin/config` ganhou a categoria **Plataforma** com o grupo
  "Interface (UI)"; trocar o valor propaga na próxima carga de página.
- **Switch, não campo de texto** — `components/UiVersaoSwitch.tsx` substitui o
  campo genérico do catálogo na categoria Plataforma (o grupo `ui` é filtrado de
  `gruposDaCategoria`): dois cartões-rádio, um clique, e o `data-ui` é aplicado
  NA HORA no `<html>` do admin — sem isso a troca só apareceria na carga
  seguinte e se lê como "não aconteceu nada".
- **Peso único 400 na v1** — a camada v1 zera os 500/600 que a v2 introduziu em
  título/destaque/botão. É o traço que torna o porte PERCEPTÍVEL: sem ele a v1
  muda só efeito decorativo (vidro, sombra, aurora) e a diferença passa
  despercebida numa tela comum.
- **`Cache-Control: no-store`** na rota e `cache: "no-store"` no fetch: sem isso
  o cache heurístico do navegador serve a versão anterior e a troca no painel
  parece não ter surtido efeito.
- **Testes** — `test_ui_versao.py` (catálogo, sanitização e resolução da flag).


## 49. Ícones do menu lateral — o slot que o design system já reservava

`.nav-item` nasceu no design system Bancada com `display:flex`, `align-items:center`
e `gap: .625rem` — a folga era para um glifo que nunca foi desenhado, e o menu ficou
14 linhas de texto mono do mesmo tamanho. Cada lente do menu profile-centric (§19)
passa a ter um ícone próprio: o gestor volta ao mesmo item pela FORMA, sem reler a
lista inteira.

- **`components/icons.tsx`** — `IconeNav` + o registro `GLIFOS` (união `NomeIcone`).
  SVG inline de 16px, `viewBox` 24, traço 1.5 em `currentColor`, mesmo padrão do
  ícone de `BotaoEspelho`. **Nenhuma biblioteca de ícones**: herdar a cor é o que faz
  o item ativo (fundo em gradiente, tinta abyss) e o hover funcionarem sem regra
  extra, e a stack da §1 não muda. Ícone é decorativo (`aria-hidden`) — quem nomeia o
  destino é o rótulo ao lado; anunciá-lo duplicaria o link no leitor de tela.
- **`.nav-icon`** (globals.css, `@layer components`): `flex-shrink: 0` (rótulo longo
  como "Agenda de contatos" não espreme o desenho) e opacidade 0.65 que sobe a 1 no
  hover e no item ativo — o glifo fica um tom abaixo do texto, nunca competindo com
  ele. Vale igual na v1 e na v2 (§48): ícone não é assinatura de versão.
- **Onde**: `app/panel/layout.tsx` — cada entrada do `NAV` declara `icone`, e o link
  "Administração" usa `admin`. Item novo no menu = mais um glifo no registro + a
  chave na entrada; o TypeScript recusa `icone` que não exista.
- **Fora do escopo por ora**: o menu de abas do shell admin e o menu por categoria de
  `/admin/config` seguem sem glifo (usam `.nav-item`, então basta o mesmo componente
  quando forem contemplados).

## 50. Carga diária do pacote SIconv — emendas parlamentares no banco

As emendas do TransfereGov não vinham de rota de API: o módulo `especiais`
**não tem endpoint de emenda** (§42 descobre rota por spec e nunca acha uma —
os campos da emenda moram dentro de `/planos_acao_especiais`), e o pacote de
dados abertos do SIconv (discricionárias e legais) publica a entidade inteira
como ZIP nacional. Agora um job diário baixa, descompacta e carrega.

- **A tabela certa é `emenda`, não `apoiadores_emendas_programas`.** No modelo
  oficial, `emenda` tem `ID_PROPOSTA` (FK → `proposta`), e é por ela que se
  chega ao `COD_MUNIC_IBGE` — a chave canônica do Hub (§4). A
  `apoiadores_emendas_programas` só tem FK para `programa`: **não existe
  caminho dela até a proposta**, então nem município ela resolve. É complemento
  (quem apoiou/indicou), não a fonte.
- **Connector** `connectors/siconv_downloads.py`: catálogo por TABELA do modelo
  (`emenda`, `proposta` carregadas; `convenio`/`empenho`/`pagamento`/
  `desembolso` mapeadas mas `carrega=False` — baixar centenas de MB sem destino
  no schema seria desperdício). O NOME do ZIP é resolvido em runtime
  (`siconv_<t>.zip` → `<t>.zip`, 404 = próximo candidato), com override no
  painel (`siconv_downloads_url`, `siconv_<tabela>_arquivo`) — §27. Download em
  streaming **para disco**: `proposta.csv` passa de 1 GB e em memória derrubaria
  o worker.
- **Job** `jobs/siconv_diario.py`: `COPY` de cada CSV para uma temp table
  `ON COMMIT DROP` (dispensa GRANT de CREATE e não gruda na conexão do pool) e
  **um** `INSERT … SELECT … ON CONFLICT` em `proposta_emendas`. O join
  `emenda → proposta` acontece no Postgres, não em Python — a memória do
  processo fica constante. Schema da staging vem do HEADER do arquivo
  (`utf-8-sig`: sem isso o BOM gruda no nome da 1ª coluna); coluna que a fonte
  renomear vira `NULL` em vez de derrubar a carga. `id_externo` =
  `ID_PROPOSTA|NR_EMENDA` — a mesma proposta acumula emendas de autores
  diferentes. Agendador próprio (`worker-siconv` no compose, 07:00 UTC),
  advisory lock contra réplica dupla, `RODAR_AGORA=1` para carga imediata,
  `sync_runs` por execução.
- **`ON CONFLICT DO UPDATE` aplica a policy de SELECT** sobre a linha nova, não
  só as de INSERT/UPDATE. Como a de `proposta_emendas` recorta por
  `municipios_interesse` e o job é global (sem tenant), TODA linha com município
  preenchido era recusada com "new row violates row-level security policy" e
  nenhuma emenda entrava. Migration `e2f3a4b5c6d7` acrescenta uma policy
  PERMISSIVE de SELECT que reconhece a bandeira `app.plataforma` (a mesma de
  `demandas`) em `proposta_emendas`, `proposta_empenhos` e `pareceres`;
  `aplicar_carga` liga a bandeira na transação. A policy por município segue
  intacta para o request do usuário — permissivas somam com OR. **Nem o owner
  escapa** (FORCE RLS): leitura administrativa dessas tabelas também precisa da
  bandeira.
- **`DISTINCT ON (id_proposta, nr_emenda)`** é obrigatório: emenda repetida no
  arquivo faz o Postgres recusar o comando inteiro ("cannot affect row a second
  time"). E **sem `RETURNING`** — ele leria sob a policy de SELECT e reportaria
  "0 gravadas" com a tabela cheia (§41); a contagem sai do `rowcount`.
- **Número BR decide pela vírgula**: `1.234,56` tem ponto de milhar, `1234.56`
  já é decimal. Converter às cegas transformaria o segundo em `123456`.
- **Cadeia de execução** (`convenio` + `empenho` → `proposta_empenhos`): o
  empenho só conhece `NR_CONVENIO`; quem sabe de que proposta — e portanto de
  que MUNICÍPIO — ele é, é o convênio (`convenio.ID_PROPOSTA`). Por isso são
  três arquivos em cadeia, e o convênio entra como PONTE mesmo sem tela própria.
  Empenho de convênio ausente do pacote entra sem território em vez de sumir: o
  documento existe. Datas aceitam `DD/MM/AAAA` e ISO via `to_date` (nunca
  `::date` cru — linha suja não aborta a carga). `valor_pago`/`valor_liquidado`
  ficam **NULL de propósito**: o pacote publica pagamento por CONVÊNIO, e ratear
  entre os empenhos daria um número que não é daquele documento — a
  `proveniencia` diz isso. Atribuir de verdade exigiria `empenho_desembolso`.
- **Recorte operacional**: `SICONV_TABELAS=emenda,proposta` restringe a carga
  (a cadeia de execução custa centenas de MB a mais por dia). Vazio = catálogo
  inteiro. `aplicar_carga` só roda o upsert cujos arquivos estão presentes —
  baixar menos degrada o escopo, não quebra o job.
- **O que a fonte NÃO publica** (e não é inventado): o **ano da emenda** —
  `NR_EMENDA` é código do autor + sequencial. Gravamos `ano` a partir de
  `proposta.ANO_PROP` para o filtro de safra funcionar e marcamos
  `proveniencia.ano = 'derivado:…'`. **Partido e UF do parlamentar** também não
  existem no pacote: vêm do connector `emendas` (Portal da Transparência).

## 51. Identidade do registro coletado — o `id_externo` é a chave do cache

Relato do gestor: "Apuiarés aparece com **1** proposta (tipo scraping) em 2026,
mas tinha 5" e "o número de propostas do município fica mudando". Não eram os
filtros nem o cache-first: eram DOIS defeitos na ingestão, ambos na identidade
do registro. `unique (fonte, id_externo)` é a chave do upsert — é por ela que a
coleta decide se ATUALIZA uma linha ou CRIA outra —, então identificador mal
formado não é cosmético: ele reescreve o cache.

- **Aglutinação perdia linha** (`connectors/_combinada.aglutinar`): o scraping
  era indexado por número e só o índice era devolvido. Linha de página SEM
  número identificável era descartada sempre que alguma OUTRA tinha número (a
  página mistura os dois casos o tempo todo), e duas linhas com o mesmo número
  colapsavam numa. Agora o índice serve APENAS para casar com a API — cada linha
  da página casa com no máximo uma da API e tudo que sobra entra como registro
  próprio. Nenhuma linha some.
- **`connectors/_identidade.py`** é a regra única: id publicado pela fonte vence;
  sem id, a identidade é o **hash do CONTEÚDO da linha, escopado no município**.
  As retaguardas antigas eram POSICIONAIS (`i`, `len(records)+1`,
  `painel-{ibge}-{i}`) — a posição muda a cada coleta, então a mesma
  transferência trocava de identidade entre rodadas — ou NÃO ESCOPADAS
  (`i` puro, `str(None)` → o id literal `"None"`): o par único é GLOBAL, então a
  proposta "1" de um município e a "1" de outro eram a MESMA linha e a proposta
  mudava de território a cada rodada. Aplicado em `serpro`, `transferegov_disc`,
  `transferegov_esp`, `transferegov_voluntarias`, `fns`, `caixa`, `simec` e
  `sismob` (`fpm`/`fns` já usavam o hash — o helper unifica).
- **Migration `a4b5c6d7e8f9`** MARCA (soft delete, §41 — nunca apaga: o cascade
  ignora RLS) as propostas gravadas com o esquema antigo, que não seriam mais
  reemitidas e ficariam órfãs, congeladas e possivelmente no município errado. É
  auto-corrigível: o upsert zera `excluido_em`, então uma linha cujo id era
  legítimo volta na coleta seguinte.
- **Regressão**: `test_contagem_municipio.py`.

### 51b. "Atualizar fontes" consulta AGORA (`forcar`)

O botão herdava o TTL de 6h do cache-first: o gestor clicava, a tela dizia
"consultando as fontes…" e nenhuma fonte era consultada. Pedido EXPLÍCITO de
atualização não pode devolver cache em silêncio.

- `consulta_avulsa.live_search(..., forcar=True)` pula o cache de dados e o de
  tentativa; `POST /proposals/live-search` aceita `forcar` e o painel o envia só
  no botão. Toda leitura AUTOMÁTICA segue cache-first — é onde ele economiza a
  coleta cara (§38).
- **Status por fonte ganhou um terceiro estado**: `ok` (consultada agora, com
  `registros` trazidos) · `erro` · **`cache`** (não foi consultada). Antes tudo
  que não falhava vinha como "ok" e a tela anunciava consulta que não houve.
- **Idade do dado na tela**: `GET /proposals` devolve `atualizado_em` (max
  `cache_atualizado_em` do recorte, via `propostas.atualizado_em`) e a Captação
  mostra "dados de há X". A lista é servida do banco e quem alimenta é o sweep
  diário (`jobs/refresh_diario`) — sem o carimbo, "o número mudou" não tem como
  ser explicado ao gestor.
## 52. `updated_at` carimbado em Python — salvar não podia "salvar para sempre"

Relato do gestor: "ao salvar uma aula do Class fica salvando eternamente e nada
acontece". Não era o editor nem a rede: **todo** `PATCH /admin/class/articles/{id}`
devolvia 500 e a transação era revertida — o botão nunca gravava nada.

- **A causa** era `updated_at` com `onupdate=func.now()` (expressão SQL): o valor
  é gerado pelo BANCO, então o SQLAlchemy EXPIRA o atributo depois do UPDATE e a
  próxima leitura vira I/O. `editar_artigo` serializa o objeto logo após o
  `flush()` — e ler um atributo expirado dentro de uma corrotina, fora do
  greenlet, é `MissingGreenlet`. Quem re-SELECIONA depois do flush escapava
  (`editar_modulo` via `modulo_por_slug`); quem devolve o objeto direto, não.
- **A correção mora no MODELO, não no router**: `models/_mixins.updated_at_col()`
  carimba em Python (`onupdate=lambda: datetime.now(UTC)`). O valor fica conhecido
  no cliente — nada expira, nada faz roundtrip extra e o UPDATE não precisa de
  RETURNING (que, sob RLS, ainda leria pela policy de SELECT — §50). Aplicado nos
  14 modelos com a coluna; fecha a mesma falha em
  `POST /assessoria/demands/{id}/comments` (comentar demanda), que quebrava igual.
- **Relacionamento não acompanha a FK**: trocar `categoria_id`/`modulo_id` NÃO
  atualiza `artigo.categoria`/`artigo.modulo` já carregados — a resposta saía com
  o módulo ANTIGO e o editor, que se repinta com ela, mostrava que nada mudou.
  `editar_artigo` faz `session.refresh(artigo)` antes de serializar.
- **A tela nunca mais fica presa**: `salvar()` em `app/admin/class/[id]` ganhou
  `try/finally` (promessa REJEITADA deixava `salvando=true` para sempre, sem
  mensagem alguma) e timeout de 60s. `lib/api/client.mensagemDaFalha()` extrai o
  `detail` do FastAPI (inclusive a lista do 422) e serve para os dois casos —
  erro retornado e erro lançado. **Handler async que liga um estado de "…ando"
  desliga no `finally`**, sempre.
- **Regressão**: `tests/test_helpdesk.py` passou a exercitar os endpoints de
  ESCRITA do admin (salvar, publicar, renomear, virar aula, mídia, hint) — antes
  só o serviço era testado e o router inteiro não tinha cobertura.

## 53. Critérios de alerta — o usuário escolhe QUAIS alterações recebe

Monitorar era tudo-ou-nada: qualquer alteração virava alerta e a central virou
ruído. Agora todo monitoramento carrega os **critérios** escolhidos num
multi-select, e a varredura emite **um alerta por critério ligado que teve fato
novo** — não um alerta genérico de "mudou alguma coisa".

- **Registro** — `services/criterios_alerta.py::CRITERIOS` é a fonte de verdade
  (chave, rótulo, descrição, escopo, padrão). Dois escopos: `proposta`
  (monitorar uma proposta-chave) e `territorio` (monitorar um município).
  Critérios de proposta: `parecer_novo` (parecer que ainda não existia),
  `parecer` (veredito de um parecer já emitido mudou), `empenho` (empenho
  emitido/valor empenhado), `empenho_pago` (pagamento/liquidação NOS
  DOCUMENTOS), `pagamento` (pago/liberado no agregado da execução), `emenda`
  (emenda aplicada à proposta ou valores dela), `publicacao` (proposta
  publicada na fonte), `vencimento` (fim de vigência), `situacao`
  (situação/movimentação), `prazo`, `pendencia`. Os pares
  `parecer_novo`×`parecer`, `empenho`×`empenho_pago` e `pagamento`×`empenho_pago`
  existem porque são avisos DIFERENTES para o gestor (emitir ≠ pagar; parecer
  novo ≠ veredito virou), e cada um observa só o seu campo do snapshot. De
  território:
  `nova_proposta`, `oportunidade`. Critério novo = uma entrada aqui — catálogo,
  validação da API e chips do front acompanham sozinhos.
- **`criterios` NULL = os padrões** (`monitoramentos.criterios` e
  `monitoramentos_busca.criterios`, migration `a1b2c3d4e5f7`): monitoramento
  criado antes da feature não perde nenhum alerta. **Lista vazia é escolha
  legítima** ("não quero nenhum") e NÃO cai no padrão — senão desmarcar tudo
  religaria o ruído inteiro.
- **Detecção por critério** (`services/detect_changes.py`, funções PURAS, sem
  banco): `snapshot()` fotografa o estado material da proposta (situação,
  movimentação, prazos, pendências, estado de publicação, empenhado/liberado/
  pago do agregado e dos documentos, pareceres POR ID + veredito, emendas por id
  e valores, fim de vigência) e `avaliar()` compara com a foto anterior —
  `monitoramentos.snapshot` (jsonb) — devolvendo uma `Mudanca(criterio,
  payload)` por critério. `CAMPOS_POR_CRITERIO` amarra campo → critério e
  `CAMPOS_DE_APOIO` marca o que existe só para a FRASE do alerta (`dias_para_
  vencer`, autores da emenda) — comparar esses geraria alerta diário sem fato
  novo. `podar()` remove do snapshot gravado os campos dos critérios DESLIGADOS
  (guardar o zero de um dado não coletado viraria "3 pareceres novos" no dia em
  que o usuário ligasse o critério).
- **Identidade, não posição**: parecer e emenda são casados por `id_externo` (ou
  hash do conteúdo). Cair no índice da lista faria toda a coleta seguinte
  parecer "tudo novo", porque a ordem muda entre rodadas — mesma disciplina da
  §51. Parecer que SUMIU da fonte não é "novo parecer", e parecer que acabou de
  entrar não conta como "veredito alterado" (sairia duplicado nos dois).
- **Publicação é ESTADO**: `publicada` é derivada do texto/valor que a fonte
  publica ("Publicado", uma data, ou `valor_publicado > 0`; "não publicado" e
  variantes contam como não). Assim "passou a publicada" vira uma frase própria
  em vez de um diff cru de campo.
- **Sem linha de base não há alerta**: a 1ª varredura só fotografa, senão a
  proposta inteira "mudaria". A exceção é `vencimento`, que é ESTADO e não
  diferença — convênio a vencer dentro de `JANELA_VENCIMENTO_DIAS` (30) avisa já
  no primeiro olhar, e depois só quando a data muda ou quando ENTRA na janela
  (`dias_para_vencer` fica fora da comparação: mudaria todo dia e alertaria todo
  dia sem fato novo).
- **Varredura** (`services/oportunidades.varredura`) ganhou a 3ª detecção,
  `_mudancas_monitoradas`: lê o cache do território (pareceres, empenhos e
  emendas só quando o critério pede — consulta ao vivo é papel da Captação) e
  cria os alertas com `tipo = <critério>` e payload `{mudou, resumo, titulo,
  numero_proposta, municipio…}`. As buscas passam a filtrar `nova_proposta` e
  `oportunidade` pelos seus próprios critérios.
- **FAVORITAR É ACOMPANHAR** (`monitoramentos.origem`, migration
  `b2c3d4e5f8a0`): favoritar cria um monitoramento `origem='favorito'` com os
  critérios padrão E com a fotografia tirada NA HORA
  (`monitoramentos_service.acompanhar_favorita`) — sem a linha de base imediata,
  a novidade que o cron trouxesse em seguida só serviria de baseline e passaria
  em branco. `garantir_das_favoritas` adota na varredura as favoritas anteriores
  à feature. Parar um acompanhamento implícito NÃO o ressuscita: o insert é
  `ON CONFLICT DO NOTHING`, então é a AUSÊNCIA de linha que autoriza criar.
- **O alerta nasce no CRON** (`jobs/alertas.py` + `jobs/refresh_diario`): logo
  depois de o refresh diário atualizar o cache DAQUELE usuário, a varredura dele
  roda na sua sessão RLS e os alertas saem pelos canais. Antes, a detecção só
  acontecia quando alguém abria a central de Alertas — o oposto do que um alerta
  serve. `varrer_todos()` existe para o cron externo (n8n) e lista os usuários a
  partir de `usuarios` (fora do RLS) DE PROPÓSITO: `set_config(..., true)` deixa
  a GUC do tenant como string VAZIA na conexão depois da transação, e aí o
  `current_setting('app.usuario_id')::uuid` das policies estoura em qualquer
  leitura sem tenant que reaproveite a conexão.
- **API**: `GET /alerts/criteria?escopo=` devolve o catálogo (é ele que alimenta
  o multi-select). `POST /monitors` e `POST /monitors/searches` aceitam
  `criterios` (chave inválida = 422 pelo validator do schema). Não há PATCH: o
  POST é **upsert** — reenviar a mesma proposta com outros critérios é como a
  tela edita a escolha.
- **Web**: `components/CriteriosAlerta.tsx` (chips multi-select + "marcar todas"
  e aviso quando o usuário zera tudo) e `ResumoCriterios` nas listas;
  `lib/alertas.ts` carrega o catálogo UMA vez por sessão e dá o rótulo por chave
  (com retaguarda estática, inclusive o tipo legado `status`). Pontos de
  configuração: o formulário de "monitorar futuras propostas" e a nova seção
  **Propostas monitoradas** em `app/panel/alerts` (que marca ★ favorita quando
  o acompanhamento veio do favorito), e o botão 🔔 do detalhe
  (`app/panel/funding/[id]`), que agora abre o multi-select em vez de ficar
  desabilitado. `DynamicIsland` e o WhatsApp (`dispatch_alerts`) leem o mesmo
  rótulo e o `resumo` do payload — "vencimento" cru não diz ao gestor que o
  convênio vence em 10 dias.

## 54. Pacote SIconv como fonte das PROPOSTAS (discricionárias e legais) + rota de operação

A §50 trouxe o pacote nacional do SIconv para o banco, mas só as **emendas**: o
`proposta.csv` era baixado apenas como JOIN, para carimbar o município. Quem
perguntava "quero TODAS as propostas do meu município" continuava dependendo da
busca ao vivo varrendo 1 GB de CSV a cada filtro do painel (§38) — e essa é a
única via, porque **a fonte não publica consulta por município para as
discricionárias/legais**: a base sai inteira, um ZIP por tabela do modelo, em
`https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/`.

- **Carga de propostas** (`jobs/siconv_diario.sql_upsert_propostas`): `stg_proposta`
  → tabela canônica `propostas`, com o de-para espelhando o do connector (§35b):
  `NR_PROPOSTA` é a referência do gestor e a data de criação é **remontada** de
  `DIA_PROP + MES_PROP + ANO_PROP` (`data_componentes`, `to_date` e nunca
  `make_date` — linha suja não pode abortar a carga). `VL_GLOBAL_PROP` é o valor
  da proposta (§46); o fim de vigência vira prazo estruturado; o registro-fonte
  entra em `dados_fonte` no MESMO formato do connector (`plano_acao.csv` = linha
  bruta), que é de onde `ano_de`/`mes_de` e o "Dados completos da fonte" leem.
- **A `fonte` é `transferegov_disc`, não uma fonte nova** (`FONTE_PROPOSTA`). A
  chave do cache é `(fonte, id_externo)` e os dois caminhos de ingestão — busca
  ao vivo e carga do pacote — leem o MESMO arquivo: fonte própria faria a mesma
  proposta aparecer duas vezes no painel. Para convergirem na mesma linha, o
  `id_externo` do connector passou a ser SEMPRE `ID_PROPOSTA` (a PK publicada);
  o nº do convênio vinha antes e isso instabilizava a identidade — a proposta
  nasce sem convênio e ganha um ao ser celebrada, trocando de `id_externo` no
  meio do caminho (a classe de defeito da §51).
- **O upsert COMPLETA, não sobrescreve**: `execucao` e `dados_fonte` são fundidos
  (`||`) com o que já estava lá, porque o painel da Visão Geral traz
  empenhado/pago/saldo que o CSV não tem. E `excluido_em = NULL`: a fonte ainda
  publica a proposta, então uma zeragem anterior (§41) é desfeita pela recoleta.
- **Escopo: `territorio` (padrão) × `nacional`** (`SICONV_PROPOSTAS_ESCOPO` no env,
  `siconv_propostas_escopo` no painel). O arquivo é nacional e o cache só é lido
  por município: carregar o país inteiro são milhões de linhas com o
  registro-fonte em jsonb junto — é decisão de operação, não default. O recorte
  entra como filtro da própria varredura (carregar e descartar depois custaria a
  carga inteira em disco). Sem nenhum município monitorado a carga grava zero e
  **diz isso no log**, em vez de gravar o país "por via das dúvidas".
- **RLS: dois bloqueios silenciosos** (migration `b5c6d7e8f9a0`). (1)
  `INSERT … ON CONFLICT DO UPDATE` aplica a policy de **SELECT** sobre a linha
  existente, e a de `propostas` recorta por município — sem uma policy PERMISSIVE
  sob a bandeira `app.plataforma`, toda proposta já cacheada era recusada com
  "new row violates row-level security policy" (mesmo tropeço da §50). (2) ler
  `municipios_interesse` (o recorte do território) exige atravessar o `FOR ALL`
  por-tenant, que sob FORCE RLS bloqueia até o owner (§41): a policy nova ali é
  **só de SELECT** e só sob a bandeira — escrita segue exclusivamente por-tenant.
  Sem as duas, a carga entregaria zero em silêncio, o pior desfecho possível.
- **Catálogo do pacote ampliado** (`connectors/siconv_downloads.ARQUIVOS`): além de
  emenda/proposta/convenio/empenho (`carrega=True`), estão mapeados programa,
  proponentes, plano de aplicação, cronogramas, termo aditivo, histórico de
  situação, licitação, obra, obtv… — baixáveis para conferência, fora da carga
  (baixar centenas de MB sem destino no schema é desperdício).
  `inspecionar()/inspecionar_todos()` sondam **sem baixar**: HEAD e, quando o CDN
  recusa HEAD, um GET com `Range` de 1 byte; devolvem nome resolvido, tamanho e o
  motivo quando nada responde ("a fonte renomeou" ≠ "a fonte caiu").
- **Rotas de operação** (`api/v1/admin_siconv.py`, superuser):
  `GET /admin/siconv/files` (catálogo + disponibilidade ao vivo + território
  monitorado + últimas cargas), `POST /admin/siconv/load` (dispara a carga, com
  recorte opcional de tabelas — tabela fora do catálogo é 422 ANTES de baixar) e
  `GET /admin/siconv/runs`. O disparo usa `asyncio.create_task` e nunca
  `BackgroundTasks` (§19b); a trava é o advisory lock do próprio `sweep`, então
  disparo manual e worker agendado não carregam em paralelo. O download **não é
  proxiado**: o catálogo devolve a URL direta da fonte — passar centenas de MB
  pela API seria pagar banda duas vezes.
- **Web**: `app/admin/siconv` — cards de escopo/território/tabelas, tabela de
  arquivos com estado real, tamanho, link de download e seleção para carga, e o
  histórico de execuções. Item "Pacote SIconv" no shell admin. O botão
  "Carregar pacote agora" também fica em `app/admin/sources` (é lá que se olha
  quando o painel está vazio, então é lá que o gatilho precisa estar).
- **O painel lê ESTA tabela.** A carga grava em `propostas` — a mesma tabela
  canônica que `services/propostas.listar` serve à Captação, ao Meu painel e ao
  copiloto —, não num depósito paralelo: por isso a `fonte` é a do connector e o
  `id_externo` converge. Regressão em `test_siconv_propostas.py`, percorrendo o
  caminho real (carga global sem tenant → leitura sob a sessão RLS do gestor,
  com ordem por `data_proposta`, filtro de safra e o território de outro
  usuário fora da lista mesmo no escopo nacional).

## 55. FNDE calibrado (SIMAD) + PAUSAR fonte pelo painel admin

Duas coisas que andam juntas: a terceira fonte de recebidos entrou em operação, e
o painel ganhou o interruptor que permite conviver com fonte de governo instável
sem que cada coleta pague o preço dela.

**FNDE — a consulta pública do SIMAD** (`connectors/fnde.py`, reescrito; o antigo
era esqueleto com `ENDPOINT = "api/repasses"  # calibrar`, uma rota que nunca
existiu — daí o 500 crônico em `sync_runs`). O FNDE **não publica API REST** das
liberações: o que existe é um formulário POST do Oracle Web Toolkit, aberto e sem
login, e — ao contrário de FNS e TransfereGov — ele responde DIRETO do IP deste
servidor (sem Cloudflare, sem geobloqueio, sem egresso).

O contrato, lido do formulário oficial (`internet_fnde.liberacoes_01_pc`):

  1. POST `internet_fnde.liberacoes_result_pc` com `p_uf` (sigla) + `p_municipio`
     (**IBGE de 6 dígitos**, sem o verificador — a mesma pegadinha do FNS, §30b) +
     `p_ano` → LISTA DE ENTIDADES do município (CNPJ, razão social);
  2. o MESMO POST com `p_cgc=<cnpj>` → as LIBERAÇÕES: data do pagamento, nº da
     **OB**, valor, programa, banco/agência/conta.

- **DOIS layouts de tabela na mesma página** e é aqui que um parse ingênuo perde
  dado em silêncio: 7 colunas (Data, OB, Valor, Programa, Banco, Agência, C/C) e
  8, quando o bloco tem parcela — o PDDE Qualidade insere "Parcela" ANTES de
  "Programa". Lendo por POSIÇÃO, a parcela ("001") era gravada como nome do
  programa. `_indice_colunas` mapeia pelo CABEÇALHO de cada bloco, e o subtítulo
  ("PDDE - PROGRAMA DINHEIRO DIRETO NA ESCOLA") vira a `categoria` da linha.
- **A DATA separa dado de enfeite**: cabeçalho, subtítulo e a linha de "Total:"
  não abrem com data — mais robusto que contar colunas num HTML de 2004.
- **ISO-8859-1** (o httpx adivinharia errado e embaralharia todo acento) e datas
  em `19/JAN/2026` (mês PT abreviado) — os dois pontos de perda silenciosa.
- **Teto e ordenação**: município grande devolve centenas de entidades (cada
  escola tem sua UEx do PDDE) e cada drill é um POST. `ordenar_entidades` põe o
  PODER PÚBLICO municipal (secretaria/prefeitura/fundo) à frente e `MAX_ENTIDADES`
  limita a rodada: o dinheiro que responde "quanto a prefeitura recebeu" entra
  sempre; a cauda entra nas coletas seguintes. Sem a ordenação, o teto se gastaria
  nas primeiras APMs em ordem alfabética.
- Registrado em `services/fontes.py` como grupo próprio (`fnde`) e em `RECEBIDOS`.
  Validado ao vivo: Fortaleza/SME = R$ 98,9 mi em 2026 (8 OBs de salário-educação);
  Apuiarés = 306 liberações em 3 exercícios.

**PAUSAR fonte (painel admin)** — mesmo desenho dos módulos (§29), agora por
CONNECTOR: estado em `configuracoes` sob `fonte_<id>`, default no catálogo
`services/fontes.py::CATALOGO_FONTES`, cache TTL 10s (a coleta consulta em laço).

- `esta_ativa(fonte)` / `filtrar_ativas(...)` são o acesso runtime; fonte FORA do
  catálogo é considerada ATIVA — o catálogo governa o que se pode pausar, não o
  que existe (connector novo não pode nascer mudo por esquecimento de cadastro).
- Aplicado nas duas portas de coleta: `consulta_avulsa.live_search` e
  `primeiro_sync.executar` (que é o que o refresh diário chama). Fonte pausada
  não é tentada — não paga timeout nem enche `sync_runs` de incidente conhecido.
- **`serpro` nasce PAUSADO** (`padrao=False`): a rota do painel Visão Geral
  responde 404 e o Qlik não é extraível (§30). Ele continua registrado e sondável
  no diagnóstico; só não entra nas rodadas.
- API: `GET /admin/sources` passou a devolver `ativa`/`pausavel`/`label` por fonte
  e `PUT /admin/sources/state` (`{fonte, ativa}`) alterna — a resposta do PUT já é
  o diagnóstico novo, então a tela não recarrega nem mantém estado divergindo do
  servidor. Fonte fora do catálogo = 422.
- Web: coluna **Coleta** em `app/admin/sources` com o chip ativa/pausada.

## 56. Feedback do gestor 28/08 — publicação tri-estado, empenho conciliado, documentos

Rodada de correções vinda do uso real (documento "Alterações no Hub Capture —
28/08"). Quatro delas mudam REGRA e não só texto; ficam registradas porque cada
uma nasceu de a tela afirmar mais do que a fonte disse.

- **Publicação é TRI-ESTADO** (`services/publicacao.py`, fonte única da regra):
  `publicado` · `nao_publicado` · **`sem_informacao`**. A regra antiga era "todo
  texto que não começa por 'não' é publicado", então um `sim` — o valor do campo
  VIZINHO ("Empenhado sim"), capturado pelo scraping ao lado do rótulo
  "Publicação" — virava "Publicado" numa proposta que o TransfereGov dava como
  Não Publicado. Agora só marcador afirmativo, DATA de publicação ou valor > 0
  contam; o desconhecido não vira afirmação. Três correções na mesma cadeia:
  (1) `normalizer._situacao_publicacao` resolve a coluna BOOLEANA (`PUBLICADO:
  sim` → "Publicado") onde o nome da coluna ainda é conhecido, e recusa `sim`
  numa coluna que deveria trazer a situação; (2) o regex do webapp
  (`pareceres_siconv`) percorre TODOS os casamentos de "Publicação" e fica com o
  primeiro que é resposta à pergunta — a página tem outros; (3) a API entrega o
  computado `PropostaRead.publicacao` (estado + rótulo + data + **origem**:
  consulta ao vivo × pacote × relatório), e a tela não interpreta mais texto cru.
  Divergência com o portal passa a ser diagnosticável em vez de discutível.
- **Empenho tem DUAS origens e o painel usa as duas**: o agregado da
  execução (`execucao.valor_empenhado`, do pacote/painel, ~mensal) e a soma das
  NOTAS (`proposta_empenhos`). O detalhe já conciliava; o resumo do painel, não —
  proposta cujo empenho só existia em nota ficava fora do card "Empenhado" com o
  documento à vista na página dela. `empenhos_proposta.totais_por_proposta`
  agrega os documentos do recorte em UMA consulta e `propostas.resumo` usa como
  retaguarda (o agregado VENCE: somar os dois contaria o mesmo dinheiro duas
  vezes). Pelo mesmo motivo a seção "Empenhos" não afirma mais "nenhum empenho
  emitido" quando o agregado informa empenho: o que falta é o documento, não a
  reserva orçamentária.
- **Documentos digitalizados** (`proposta_documentos`, migration `c1d2e3f4a5b6`):
  publicou → cadê o arquivo. A lista vive na MESMA página de detalhe do webapp
  SIconv que já visitamos (`parse_documentos`, sem navegação nova, também no
  lote do enriquecimento). Guardamos a REFERÊNCIA (nome, data, URL na fonte),
  nunca os bytes — o arquivo é público na origem e cachear binário de terceiro
  cria acervo que ninguém pediu para manter. A espécie sai do NOME por palavra
  inteira (`normalizer_documento.classificar`; "contrato" está dentro de
  "subcontratado"), e a publicação lidera a lista. `GET /proposals/{id}/documents`
  com o gate por endpoint da §40; seção `components/DocumentosProposta.tsx` no
  detalhe. Fonte sem essa lista responde `fonte_nao_suportada` — que é diferente
  de "esta proposta não tem documento", e a tela precisa dessa diferença.
- **Os cards do painel viram FILTRO** (ponto 06): total · empenhado · publicado ·
  pago deixaram de ser leitura pura — clicar recorta o feed pelas propostas que
  compõem o número (`propostas.estados_de`/`filtrar_por_estado`,
  `GET /profile/feed?estado=`). Os totais continuam sendo os do TERRITÓRIO: card
  que se recalculasse ao ser clicado apagaria o próprio rótulo e prenderia o
  gestor no recorte (mesma disciplina das facetas). Recorte ligado esconde os
  repasses — dinheiro que já caiu não tem empenho nem publicação. Estado
  desconhecido devolve tudo, nunca vazio.

Junto vieram as correções de superfície: o critério de alerta **"Oportunidades
não aproveitadas" foi RETIRADO** (repasse sem proposta na mesma fonte é o normal
do repasse constitucional — disparava sempre; alertas já gravados seguem legíveis
por `criterios_alerta.RETIRADOS`); o critério `publicacao` virou **"Publicação"**
e cada fato ganhou sua frase (o alerta saía rotulado "Proposta publicada" com o
texto "publicação atualizado(s)" para uma proposta NÃO publicada); e o **"Detalhe
técnico (para a administração)"** — rota, exceção, parâmetro a calibrar — só
aparece para `is_superuser` (`lib/admin.ts::useEhAdmin`), com o gestor lendo
"Não foi possível consultar a fonte agora". Textos de mecânica saíram do
cabeçalho da Captação e do título da lista do painel.

**Fora desta rodada, por decisão do cliente**: o funcionamento das abas
Oportunidades e Regularidade (Fase 2 do `docs/PLANO_MELHORIAS_APP.md`, §2.5/§2.7).
**Pendente de calibração ao vivo** (exige máquina com saída para gov.br): a
extração da lista de documentos e a confirmação da causa raiz do "Publicado"
divergente — o endurecimento acima cobre as duas hipóteses, mas só o probe contra
a fonte fecha a questão.

## 57. Design system v1 "Hub Capture" — a migração da Bancada v2 (decisão travada)

A UI saiu da **"Bancada v2"** (canvas quase-preto com aurora, cards de vidro,
rótulos em Roboto Mono caixa-alta de 11px, peso único 400) para o **design
system v1**, aprovado a partir da alternativa C dos previews com ressalvas. O
guia renderizado é `/previews/guia.html` (fonte de verdade de cor, tipografia,
forma e componentes) e a tela de referência é `/previews/hub.html`.

- **Paleta** — acento `#43CF9B` · escuro `#031918` · auxiliares `#1C6555`
  (ação) e `#1B6255` (hover). Semânticas: `ok #1C6555` · `warn #E0A82E`
  (texto `#96660F`) · `danger #C0392B` · `info #2A7F9E`. O acento **nunca
  legenda texto sobre branco** (1,9:1): é preenchimento com tinta escura,
  linha, anel de foco ou marcador.
- **Dois temas de verdade.** Claro: canvas `#F3F7F5`, cards brancos (a
  separação é a sombra `0 0 30px rgba(3,25,24,.08)`), tinta `#1F2A27`.
  Escuro: canvas `#08201E`, cards `#0E2A27` **com borda** (sombra não separa
  sobre fundo escuro) e a AÇÃO passa a ser o acento — o `#1C6555` não se
  destaca do fundo escuro. O trilho lateral é `#031918` nos DOIS temas: é
  onde a marca aparece.
- **`--grad-brand` × `--fill-accent`**: o gradiente é só a superfície de
  DESTAQUE (tinta da cor → branco, 135°, um por bloco). Preenchimento e traço
  (chip ativo, barra de progresso, `.btn-accent`, filete de linha, sublinhado)
  usam `--fill-accent` sólido — com o gradiente, que é translúcido no escuro,
  o chip ativo e a barra sumiam.
- **Tipografia**: **Archivo** em H1–H3 (CAIXA ALTA com tracking) e nos
  números; **Inter** no corpo e na UI. A Roboto Mono saiu do sistema, mas
  `--font-mono` continua definido apontando para a Inter: ~200 rótulos do app
  chamam `font-mono`, e removê-lo trocaria a face por serifada. Botão, corpo
  e descrição NUNCA vão em caixa alta.
- **Aliases depreciados**: `--color-lime/aqua/abyss/bone/graphite/lichen/
  tissue` seguem no `@theme` apontando para a paleta nova. ~55 utilitários
  (`bg-lime`, `text-abyss`) ainda os usam e, sem o nome, o Tailwind compila
  para NADA e o elemento some em silêncio. Ao tocar uma tela, trocar pelo
  nome novo.
- **Disposição (§7 do guia)** — `app-shell` é uma GRADE (sidebar 272px +
  conteúdo), não mais um trilho arredondado flutuando dentro do padding: a
  sidebar encosta na borda, tem altura cheia e vira gaveta abaixo de 1024px;
  o header branco de 60px carrega a trilha (território → tela) e o papel. O
  **admin** ganhou o mesmo shell, com os 11 destinos agrupados em Pessoas ·
  Plataforma · Dados · Conteúdo — antes eram onze pílulas numa linha só, que
  quebrava em duas no notebook e não dizia o que era o quê.
- **`.sidebar X` fora de `@layer`**: um override de utilitário do Tailwind
  (`text-ink`, `border-hairline`) dentro de `@layer components` PERDE para a
  layer `utilities`. Com ele lá dentro, o nome do município sumia na sidebar
  do tema claro (tinta escura sobre verde escuro). As regras do trilho ficam
  num bloco sem camada, no fim do arquivo — mesma disciplina da camada v1.
- **Componentes**: `StatusBadge` virou badge SÓLIDO (a cor é a informação);
  antes eram quatro estados com a mesma cara de contorno cinza. `StatCard`
  usa `.stat-label` (o H3 do sistema) e o contexto em caixa de frase.
- **A flag `ui_versao` (§48) continua**: o novo sistema é o padrão (`v2`) e a
  camada `v1` segue como o porte FLAT do mesmo sistema — superfícies sem
  sombra/gradiente. Nenhuma mudança de contrato na API.
- **Aberto**: a arte de `/public/login-hero.jpg` ainda é da paleta antiga
  (topografia em lime amarelado); regerar no verde da marca.
