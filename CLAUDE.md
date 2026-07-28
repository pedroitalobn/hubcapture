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
- Web: `app/admin/config` (agrupado por categoria; segredos em campo password, mascarados).

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
- **Endpoint** — `POST /copilot/island` (SSE): o loop de tools roda ANTES do stream
  (sessão RLS do request precisa estar viva); eventos `{"tool": nome}` e
  `{"delta": texto}`. Client web: `islandStream` em `lib/api/client.ts`.
- Adicionar ferramenta = nova entrada em `ai/agent.py::TOOLS` (descrição + JSON
  schema + executor + gatilhos de fallback); o front mostra o chip automaticamente
  (rotule em `DynamicIsland.tsx::TOOL_CHIP`).

## 25. Rotas em INGLÊS (decisão travada) + Captação em tempo real

- **Todas as rotas são em inglês** — API v1 e páginas web. De-para principal:
  propostas→proposals · consulta-avulsa→proposals/live-search · repasses→transfers ·
  conformidade→compliance · obras→works · alertas→alerts (lido→read, varredura→scan) ·
  favoritos→favorites · pastas→folders · monitoramentos→monitors (buscas→searches) ·
  perfil→profile (visao-geral→overview, novidades→feed) · municipios→municipalities ·
  noticias→news · copiloto→copilot · planos→plans · admin/usuarios→admin/users ·
  convites→invites · fontes→sources · conhecimento→knowledge · aceitar-convite→accept-invite.
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
  `proposals` (captacao), `transfers` (recebidos), `compliance`, `works` e `copilot`.
  O guard roda ANTES da autenticação (dependency de router), então o eixo simplesmente
  não existe enquanto desligado.
- **Endpoints admin** (`is_superuser`): `GET /admin/modules` (catálogo + estado efetivo)
  e `PUT /admin/modules` (`{chave, ativo}`). Router `api/v1/admin_modulos.py`.
- **Perfil** — `GET /profile` passa a devolver `modulos` (lista dos ativos) e
  `GET /profile/overview` só agrega/retorna as dimensões dos módulos ativos (módulo
  desligado nem é consultado no banco).
- **Web** — `app/admin/modules` (toggle por módulo, no shell admin da seção 24); o menu
  de `app/panel/layout.tsx` filtra os itens por `perfil.modulos`;
  `components/ModuloGate.tsx` cobre o acesso direto por URL às telas de eixo desligado
  (explica em vez de mostrar tela vazia).
