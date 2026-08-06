# Hub Capture — Arquitetura Técnica e Fluxograma

> Concentrador de propostas/editais e solicitações das plataformas do governo brasileiro.
> Curadoria por IA, monitoramento ativo, multi-fonte, multi-município, com notificações via WhatsApp.
>
> **Documento de arquitetura — v2 (base para desenvolvimento)**
> Calibrado nos endpoints oficiais do DTPAR/TransfereGov e nas features da apresentação do Hub Propostas.

---

## 1. Visão geral em uma frase

O usuário (parlamentar, chefe de executivo ou equipe administrativa) assina, escolhe um nível de acesso, passa por um **onboarding conversacional** que captura município(s) e fontes de interesse, e a partir daí recebe **propostas curadas por IA**, podendo **favoritar, agrupar em pastas, monitorar** e **conversar via WhatsApp** — tudo alimentado por um cache próprio que sincroniza diariamente com as fontes oficiais (D-1) — e podendo também fazer **consultas avulsas on-demand** de municípios que não monitora.

---

## 2. Princípios de arquitetura

| Princípio | Decisão | Porquê |
|---|---|---|
| **Cache próprio, não consulta ao vivo** | Sync agendado popula nosso Postgres; o usuário consulta nosso banco | As fontes atualizam D-1 (dado do dia anterior) e a API oficial é instável (vimos 502 em produção). Consultar nosso cache é rápido, resiliente e permite monitoramento. |
| **Conectores plugáveis** | Cada fonte é um *connector* isolado com interface comum | Novas fontes (estaduais, emendas, convênios) entram sem reescrever o core. |
| **Coleta combinada (API + scraping)** | Rodam juntos e fazem merge: API traz estrutura, scraping enriquece e atualiza. Fallback é caso particular | Soma de informação > qualquer fonte sozinha. Discricionárias só tem CSV; FNS não tem API; e a API que existe é D-1 e cai. |
| **Normalização canônica** | Toda fonte vira um schema único `Proposta` | Painel multi-fonte só funciona se tudo falar a mesma língua. |
| **Multi-tenancy por usuário** | Tenant = usuário individual. RLS por `usuario_id`; escopo de dados = municípios cadastrados | Assinatura pessoal. Banco único, sem org nesta fase (extensível depois). |
| **Dois modos de consulta** | Agendado (cron, popula cache, alimenta monitor) + avulso (on-demand cache-first) | O user monitora municípios fixos E consulta avulsamente municípios que não monitora. |
| **API pública única (v1)** | FastAPI versionada, JWT, OpenAPI — web e mobile consomem a mesma | Mobile (Android/iOS) precisa de contrato estável; BFF web não serve mobile. |
| **IA como camada, não como acoplamento** | Copiloto e Resumo são serviços; o resto funciona sem eles | Se o LLM cair, o Hub continua entregando dados. |

---

## 3. Stack consolidada (mobile-ready)

> Decisões fechadas: API pública v1 em FastAPI (consumida por web + Android + iOS), Next.js como camada de apresentação, multi-tenancy por usuário individual, dois modos de consulta (agendado + avulso).

| Camada | Tecnologia | Papel |
|---|---|---|
| **Monorepo** | Turborepo 2.x | Web + serviço Python + workers num repo |
| **API pública v1 + IA + ingestão** | **FastAPI (Python 3.12)** | Única porta de dados. OpenAPI automático → client tipado p/ web e mobile. Auth JWT. |
| **Orquestração de agentes** | LangGraph + LiteLLM | Copiloto, resumo, chat com propostas |
| **Scraping fallback** | Crawl4AI + Firecrawl | Extrai dados de URLs quando a API falha/inexiste |
| **Web (site + BFF fino)** | Next.js 15 / React 19 + Tailwind 4 + shadcn/ui | Apresentação. Consome a API v1 — não duplica lógica de negócio. |
| **Mobile (fase 2)** | Expo (React Native) | Consome a MESMA API v1 |
| **Auth** | JWT no FastAPI (fastapi-users) | Fonte única de verdade p/ auth e RLS |
| **Banco** | Postgres (Neon) 16 + pgvector | Propostas, usuários, pastas, embeddings |
| **ORM** | SQLAlchemy 2 + Alembic | Migrations versionadas |
| **Jobs/orquestração** | n8n | Cron de sync · detect_changes · dispatch_alerts · Uniq |
| **Fila** | Redis + ARQ (ou Celery) | Sync pesado, retries, processamento de alertas (lado Python) |
| **WhatsApp** | Uniq.chat | Alertas + chat conversacional |
| **Infra** | VPS + Dokploy (containers) | Já existente |

### Por que esta divisão
- **FastAPI como API pública**: unifica dados + IA + ingestão num runtime; OpenAPI gera client tipado para os 3 clientes (web, Android, iOS) a partir de um contrato único; Pydantic valida entrada/saída de graça.
- **Next.js só apresentação**: o painel muda muito e ganha com o ecossistema React; mas não fala com fonte de governo nem com LLM — chama a API v1 com o token do usuário.
- **Mobile-ready desde já**: a API v1 é versionada e estável (`/api/v1/...`), com auth por token (não cookie de browser). O BFF web é separado e pode mudar sem quebrar o app.
- **Auth e RLS só no FastAPI**: uma fonte de verdade — mais seguro e auditável.

### Contrato da API pública (exemplos)
```
POST /api/v1/auth/login                 → JWT
GET  /api/v1/propostas?municipio=...&fonte=...&situacao=...   (cache-first)
GET  /api/v1/propostas/{id}
POST /api/v1/consulta-avulsa            → fetch on-demand de fonte específica
GET  /api/v1/favoritos · POST · DELETE
GET  /api/v1/pastas · POST · PATCH
POST /api/v1/monitoramentos             → ativa monitoramento de uma proposta
GET  /api/v1/alertas
POST /api/v1/copiloto/chat              → SSE/stream (RAG)
POST /api/v1/onboarding                 → grava municípios/fontes + dispara 1º sync
```
Todos os endpoints aplicam RLS por `usuario_id` no banco. OpenAPI servido em `/api/v1/openapi.json` → Swift/Kotlin client gerado automaticamente.


---

## 4. Macroarquitetura (camadas)

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLIENTES                                                            │
│  Web (Next.js)   ·   Android (Expo)   ·   iOS (Expo)   [fase 2]      │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  consomem a MESMA API v1 (JWT)
┌───────────────────────────────▼─────────────────────────────────────┐
│  API PÚBLICA v1  (FastAPI)                                           │
│  /api/v1/...  · OpenAPI · JWT · RLS por usuario_id                   │
│  ├─ propostas (cache-first)   ├─ consulta-avulsa (on-demand)         │
│  ├─ favoritos · pastas        ├─ monitoramentos · alertas            │
│  └─ copiloto/chat (stream)    └─ onboarding (dispara 1º sync)        │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
┌───────▼─────────┐  ┌───────────▼──────────┐  ┌──────────▼──────────┐
│  MOTOR HUB      │  │  CAMADA DE IA        │  │  CAMADA DE INGESTÃO │
│  Normalização   │  │  Copiloto · Resumo   │  │  Connector Registry │
│  Dedup · diff   │  │  Chat c/ propostas   │  │  API|CSV|Crawl4AI   │
│  Embeddings     │  │  (LangGraph+RAG)     │  │  retry·breaker·fallb│
└───────┬─────────┘  └──────────────────────┘  └──────────┬──────────┘
        │                                                  │
        │                    ┌─────────────────────────────┘
        ▼                    ▼              ▲ FONTES OFICIAIS
┌─────────────────────────────────────┐    │ TransfereGov (API+CSV)
│  PERSISTÊNCIA (Postgres/Neon)        │    │ FNS · FNDE · SERPRO
│  + pgvector                          │    │ [+ fontes futuras]
│  propostas · usuarios · pastas       │
│  favoritos · monitoramentos · alertas│
│  municipios_interesse · embeddings   │
└──────────────────────────────────────┘

   ORQUESTRAÇÃO (n8n) ──► cron de sync · detect_changes · dispatch_alerts
                          └─► NOTIFICAÇÃO: Uniq → WhatsApp (alertas + chat IA)
```

> O **Next.js** não acessa banco nem fonte de governo: ele chama a **API v1** com o token do usuário, igual ao mobile. Lógica de negócio mora só no FastAPI.

---

## 5. Camada de ingestão — conectores (o coração do diferencial)

Cada fonte implementa a mesma interface:

```python
class Connector(Protocol):
    source_id: str
    def fetch(self, municipio_ibge: str, since: date) -> list[RawRecord]: ...
    def health_check(self) -> bool: ...
```

### 5.0 Os dois modos de consulta (cache-first)

O mesmo connector serve dois fluxos. A diferença é **quando** ele roda.

```
A) AGENDADO (padrão — municípios que o user monitora)
   onboarding grava municipios_interesse
        → n8n cron dispara sync diário (D-1) só desses municípios
        → popula cache → alimenta monitoramento e alertas

B) AVULSO / ON-DEMAND (municípios que o user NÃO monitora)
   GET /api/v1/propostas?municipio=X   ou   POST /api/v1/consulta-avulsa
        → 1. tem no cache e fresco (< TTL)?  → devolve na hora
           2. não tem / está velho?          → fetch ao vivo da fonte
              → normaliza → grava no cache → devolve
        → opcional: "salvar/monitorar" converte avulso em agendado
```

Regra: **toda leitura passa pelo cache primeiro**. O fetch ao vivo é exceção (cache miss ou stale), nunca o caminho padrão — protege contra a instabilidade da API oficial e mantém a resposta rápida.

### 5.1 Connector: TransfereGov — Fundo a Fundo  ✅ API REST confirmada (responde em produção)
- Base: `https://api.transferegov.gestao.gov.br/fundoafundo/`
- Endpoints: `programa`, `programa_beneficiario`, `programa_gestao_agil`, `plano_acao`, `plano_acao_dado_bancario`, `plano_acao_meta`
- Sintaxe PostgREST. Ex.:
  `…/fundoafundo/programa?nome_orgao_superior_programa=in.("Ministério do Turismo")`
- Filtro por município via campos do `plano_acao` / beneficiário.

### 5.2 Connector: TransfereGov — Transferências Especiais  ✅ API REST (instável → fallback)
- Base: `https://api.transferegov.gestao.gov.br/transferenciasespeciais/`
- Endpoints: `programa_especial`, `plano_acao_especial`, `empenho_especial`, `documento_habil_especial`, `ordem_pagamento_ordem_bancaria_especial`
- Ex.: `…/programa_especial?ano_programa=eq.2023`
- **Observação:** retornou 502 nos testes → este connector PRECISA de retry + fallback Firecrawl no painel gerencial.

### 5.3 Connector: TransfereGov — Discricionárias e Legais  ⚠️ Sem API REST
- **Não há endpoint REST.** Só download de **CSV diário**:
  `http://repositorio.dados.gov.br/seges/detru/`
- Implementação: **CSV Loader** agendado (baixa, parseia, normaliza). Não é chamada HTTP por proposta.
- Campos do CSV: `NR_CONVENIO`, `ID_PROPOSTA`, `DIA/MES/ANO`, `SITUACAO`, `INSTRUMENTO`, `UG_EMITENTE`, etc.

### 5.4 Connector: Fundo Nacional de Saúde (FNS)  ⚠️ Scraping
- Portal de consultas FNS não expõe API aberta documentada → **Crawl4AI/Firecrawl** sobre as URLs de consulta. Aqui o scraping é a fonte primária (não há API), mas ainda passa pelo mesmo pipeline de normalização e merge.
- Entregar dados "mastigados": o scraper extrai → normaliza → vira `Proposta`.

### 5.5 Connector: FNDE (Educação)  ✅ API + scraping (merge)
- Programas/propostas de educação. API (estrutura) **+** scraping (enriquecimento) combinados via merge da seção 5.7.

### 5.6 Connector: Acesso SERPRO  ✅ API direta
- Base de transferências via SERPRO para **cruzamento e enriquecimento** (não é fonte primária de proposta, é enrichment).

### 5.7 Estratégia de coleta: merge multi-fonte (API + scraping combinados)

API e scraping **não são alternativas** — são fontes complementares que rodam juntas e se **somam** numa proposta mais rica. A API traz os campos estruturados com precisão; o scraping captura o que a API não expõe (detalhes do processo, pendências em texto, última movimentação, anexos). O fallback vira um caso particular: se uma das duas falhar, usa-se a outra.

```
coletar(fonte, municipio):
    dados_api    = None
    dados_scrape = None

    # 1. API (quando existe) — retry 3x, backoff
    if fonte.tem_api:
        try: dados_api = api_client.get(...)
        except (Timeout, 5xx, RateLimit): registrar_incidente(fonte)

    # 2. Scraping em paralelo — enriquecimento, não só fallback
    if fonte.tem_url_consulta:
        try: dados_scrape = crawl4ai.extract(url)   # ou firecrawl
        except ScrapeError: registrar_incidente(fonte)

    # 3. Merge com proveniência
    if dados_api and dados_scrape: return merge(dados_api, dados_scrape)
    if dados_api:    return normalizar(dados_api)      # scraping caiu → degrada
    if dados_scrape: return normalizar(dados_scrape)   # API caiu → fallback
    marcar_fonte_degradada(fonte)
```

#### Regra de merge (quando os dois retornam)

```
merge(api, scrape):
    # Campos estruturais → API vence (precisão em números, IDs, datas)
    proposta.id_externo      = api.id_externo
    proposta.valor_total     = api.valor_total
    proposta.datas           = api.datas
    proposta.numero_proposta = api.numero_proposta

    # Campos descritivos/situação → SCRAPING vence em conflito (mais atual)
    proposta.situacao    = scrape.situacao    or api.situacao
    proposta.pendencias  = scrape.pendencias  or api.pendencias
    proposta.movimentacao= scrape.movimentacao

    # Campos só de uma fonte → entram como vierem (a soma de informação)
    proposta += campos_exclusivos(api) + campos_exclusivos(scrape)

    # Proveniência: registra de onde veio cada valor (auditoria)
    proposta.proveniencia = { campo: fonte_que_forneceu }
    return proposta
```

**Precedência em conflito: scraping > API** — porque a API é D-1 (dado de ontem) e o scraping lê o portal em tempo real. Salvaguardas:
- Vale só para campos **descritivos** (situação, pendências, movimentação). **IDs, valores e datas continuam vindo da API** — o scraping erra mais no parsing desses.
- Toda divergência é registrada em `proveniencia`, então um scraper quebrado é auditável e não corrompe o dado em silêncio.
- Se o scraping falhar, cai para o valor da API (degradação graciosa). Se a API falhar, o scraping assume sozinho (fallback).

---

## 6. Schema canônico `Proposta` (normalização)

Independente da fonte, tudo converge para:

```
Proposta
├── id (uuid interno)
├── fonte (transferegov_ff | transferegov_esp | transferegov_disc | fns | fnde | serpro)
├── id_externo (NR_CONVENIO / id_programa / id_plano_acao…)
├── numero_proposta        (ex: 043210/2025)
├── ano                    (ano de CRIAÇÃO na fonte — chave da classificação por safra)
├── titulo / objeto
├── orgao_superior         (FNS, FNDE, MTur…)
├── modalidade             (Voluntária, Fundo a Fundo, Especial…)
├── municipio_ibge / municipio_nome / uf
├── valor_total
├── contrapartida
├── situacao               (Em análise, Pendente, Aprovada, Em execução…)
├── emenda (nº)
├── prazos[]               (diligência, resposta — com data-limite)
├── pendencias[]
├── movimentacao           (última movimentação — tipicamente do scraping)
├── data_criacao_fonte     (quando a proposta nasceu na fonte — origem do `ano`)
├── data_atualizacao_fonte (D-1 — recência de movimentação; NUNCA classifica por ano)
├── url_origem
├── proveniencia {campo: fonte}   (api | scrape — auditoria do merge)
├── resumo_ia              (gerado pelo Motor Hub)
├── embedding (vector)     (pgvector)
└── hash_conteudo          (para detecção de mudança)
```

> O merge multi-fonte (seção 5.7) popula estes campos: estrutura vem da API, situação/pendências/movimentação do scraping. `proveniencia` registra a origem de cada valor para auditoria.

A **detecção de mudança** compara `hash_conteudo` a cada sync → se mudou status/prazo/pendência e a proposta está **monitorada** por algum usuário → gera **alerta**.

---

## 7. Fluxo de onboarding conversacional (wizard)

```
Assinou → escolhe NÍVEL DE ACESSO (papel)
   │
   ▼
Wizard conversacional (Copiloto conduz):
   1. "Qual seu papel?"  → Parlamentar / Chefe Executivo / Equipe
   2. "Quais municípios te interessam?"  → busca IBGE, multi-seleção
   3. "Quais fontes/áreas?"  → Saúde(FNS), Educação(FNDE), TransfereGov, todas
   4. "Quer monitoramento ativo?"  → sim/não
   5. "Conectar WhatsApp p/ alertas?"  → fluxo Uniq (opt-in)
   │
   ▼
Sistema dispara PRIMEIRO SYNC dirigido (só municípios/fontes escolhidos)
   │
   ▼
Painel já abre POPULADO com propostas curadas + resumo por IA
```

O wizard grava em `municipios_interesse` e `preferencias_usuario`, que viram **filtro de Row-Level Security** e **escopo do sync**.

---

## 8. Camada de IA

### 8.1 Resumo por IA (no Motor Hub, no momento da ingestão/atualização)
- Para cada `Proposta` nova/alterada: gera o parágrafo-resumo (valor, contrapartida, órgão, situação, pendência, prazo) **adaptado ao nível de acesso**.
- Roda em batch no pipeline de sync — não no clique do usuário (resposta instantânea no painel).

### 8.2 Copiloto interno (LangGraph + RAG)
- "Ensina passos", sugere tutoriais/vídeos, explica o que é cada tipo de transferência.
- Base de conhecimento própria (docs do TransfereGov, FAQs) indexada em pgvector.

### 8.3 Chat com as propostas (RAG sobre o banco do usuário)
- "Quais propostas de saúde do meu município vencem este mês?"
- Recupera por embedding + filtros estruturados (RLS por município/papel) → responde em linguagem natural.
- Mesmo motor serve o **chat no painel** e o **chat no WhatsApp** (via Uniq).

---

## 9. Integração WhatsApp (Uniq)

```
n8n (orquestrador)
 ├── Trigger 1: alerta de monitoramento → formata msg → Uniq → WhatsApp do gestor
 └── Trigger 2: usuário manda msg no WhatsApp
         → Uniq webhook → n8n → Camada de IA (chat c/ propostas, com RLS do user)
         → resposta → Uniq → usuário
```

- Opt-in capturado no onboarding.
- Vínculo `telefone ↔ usuario` para aplicar o escopo de acesso certo nas respostas.

---

## 10. Integração mobile (Expo ↔ API v1)

O app mobile é um **cliente da mesma API v1**, igual ao web. Expo (TypeScript) e FastAPI (Python) são camadas independentes que conversam por HTTP/JSON — a linguagem do backend é invisível pro app.

```
Expo (TS)  ──HTTP/JSON (JWT)──►  FastAPI /api/v1  ──►  Postgres
   ▲                                   │
   └── client TS tipado, gerado do OpenAPI da própria API
```

### 10.1 Client tipado gerado do OpenAPI
A API expõe `/api/v1/openapi.json`. O app gera um client TypeScript a partir dele — endpoint escrito uma vez em Python vira função tipada no mobile e no web.

```bash
# no app mobile (e no web, mesma técnica)
npx openapi-typescript http://API_HOST/api/v1/openapi.json -o src/api/schema.d.ts
```
```ts
import createClient from "openapi-fetch";
import type { paths } from "./api/schema";

export const api = createClient<paths>({ baseUrl: "https://API_HOST/api/v1" });

// uso tipado — TS acusa se um campo mudar na API
const { data } = await api.GET("/propostas", {
  params: { query: { municipio: "2301109", fonte: "fns" } },
  headers: { Authorization: `Bearer ${token}` },
});
```
Mudou um campo no FastAPI? Regenera o schema → o TypeScript aponta o que quebrou, no web e no mobile ao mesmo tempo.

### 10.2 Auth por token (não cookie)
App não tem cookie de sessão de browser. Usa **JWT no header** `Authorization: Bearer <token>`, guardado de forma segura:
- token em `expo-secure-store` (Keychain no iOS, Keystore no Android), nunca em AsyncStorage puro.
- refresh token para renovar sem novo login.
- A mesma RLS por `usuario_id` do FastAPI vale: o app só enxerga os dados do dono do token.

### 10.3 Streaming do Copiloto no mobile
O chat usa SSE. O `EventSource` nativo do React Native é limitado → usar `react-native-sse` (ou fetch com leitura de stream) para consumir `/api/v1/copiloto/chat`. Detalhe de implementação, não de arquitetura.

### 10.4 Notas de dev
- **URL base:** em dev no celular físico, apontar pro IP da máquina (não `localhost`) ou usar túnel (Expo tunnel / ngrok).
- **CORS:** liberar a origem do app no FastAPI (em mobile o que importa é a URL pública da API estar acessível).
- **Reaproveitamento:** como web e mobile consomem o mesmo contrato, dá pra compartilhar tipos e até hooks de dados num pacote do Turborepo (`packages/api-client`).

> Conclusão: a escolha de FastAPI não limita o mobile — o OpenAPI dele é justamente o que torna o Expo mais produtivo. Nenhum backend precisa ser reescrito quando o app entrar na fase 2.

---

## 11. Modelo de dados (tabelas principais)

```
usuarios(id, nome, email, papel, plano, telefone_whatsapp, optin_wpp)
municipios_interesse(usuario_id, ibge, nome, uf, modo)   -- modo: monitorado | avulso
preferencias_usuario(usuario_id, fontes[], areas[], monitorar_ativo)
propostas(… schema canônico da seção 6 …, cache_atualizado_em)   -- p/ TTL cache-first
favoritos(usuario_id, proposta_id, criado_em)
pastas(id, usuario_id, nome, cor)
pasta_propostas(pasta_id, proposta_id)
monitoramentos(usuario_id, proposta_id, ativo, canais[])  -- painel/email/wpp
alertas(id, usuario_id, proposta_id, tipo, payload, lido, criado_em)
sync_runs(id, usuario_id, fonte, tipo, status, registros, iniciado_em, finalizado_em, erro)  -- tipo: agendado | avulso
embeddings(proposta_id, vector)
audit_log(usuario_id, acao, entidade, criado_em)
```

**RLS (multi-tenancy por usuário):** toda query carrega `usuario_id` do JWT. O usuário só lê propostas dos seus `municipios_interesse` (monitorados ou já consultados avulsamente). Os campos visíveis no resumo variam por `papel`. Como tenant = usuário individual, não há tabela de organização nesta fase — mas o `usuario_id` como chave de isolamento deixa o caminho aberto pra agrupar usuários em org no futuro sem migração destrutiva.

> A mesma RLS protege web e mobile: ambos mandam o JWT, o FastAPI resolve o escopo. Nenhum cliente vê dado de outro usuário.

---

## 12. Orquestração de sync (n8n)

| Job | Frequência | Ação |
|---|---|---|
| `sync_transferegov_ff` | diário (após D-1 publicar) | puxa API Fundo a Fundo dos municípios ativos |
| `sync_transferegov_esp` | diário | puxa Especiais (com fallback) |
| `sync_transferegov_disc` | diário | baixa CSV `detru` e carrega |
| `sync_fns` | diário | Firecrawl sobre portal FNS |
| `sync_fnde` | diário | API + scraping |
| `enrich_serpro` | diário | cruza/enriquece propostas existentes |
| `detect_changes` | após cada sync | compara hash → gera alertas |
| `dispatch_alerts` | contínuo | envia alertas pendentes (painel/email/Uniq) |
| `embed_new` | após cada sync | gera embeddings das propostas novas/alteradas |
| `consulta_avulsa` | sob demanda (API) | fetch ao vivo no cache miss/stale → normaliza → cacheia |

---

## 13. Roadmap por fase

**v0 (MVP — base da apresentação)**
- API pública v1 (FastAPI + OpenAPI + JWT) — já desenhada mobile-ready
- Onboarding conversacional + 3 papéis + multi-município
- Dois modos de consulta: agendado (cron) + avulso (cache-first on-demand)
- Conectores: TransfereGov (FF + Esp + Disc/CSV), FNS, FNDE, SERPRO
- Fallback Firecrawl/Crawl4AI
- Normalização + Resumo por IA
- Painel multi-município, busca/filtros, favoritos, pastas, tabs
- Monitoramento de propostas-chave + alertas (painel/email)
- Exportar PDF
- Multi-tenancy por usuário (RLS por usuario_id)

**v1 (logo após)**
- Copiloto interno (passos/tutoriais)
- Alertas + chat via WhatsApp (Uniq)
- Chat com as propostas (RAG)

**v2+**
- **App mobile (Expo/Android+iOS)** — consome a API v1 já existente (sem reescrever backend)
- Agenda de prazos · Painel de captação (ranking/% aprovação) · Mapa por território
- Multiusuário + comentários · Workflow de resposta a diligências
- Novas fontes (estaduais/municipais) · Obrasgov.br

---

## 14. Riscos técnicos e mitigação

| Risco | Mitigação |
|---|---|
| API oficial cai (502 visto) | Retry + circuit breaker + fallback scraping + cache D-1 |
| FNS sem API muda layout | Crawl4AI com schema tolerante + alarme de "scraper quebrado" |
| Mapeamento município ↔ proposta inconsistente entre fontes | Tabela de DE-PARA por código IBGE/UG; enrichment via SERPRO |
| Volume de propostas por sync | Sync incremental (`since`), só municípios ativos |
| LLM caro/lento no resumo | Resumo em batch no pipeline, modelo menor (Haiku) p/ resumo, maior só no chat |
| Dado sensível por papel vazar | RLS no banco + filtro de campos no resumo por papel |

---

## 15. Próximos passos concretos
1. Definir o **DE-PARA de município** (código IBGE como chave canônica).
2. Subir o **connector Fundo a Fundo** (já responde) como primeiro vertical de ponta a ponta.
3. Modelar o Postgres (seção 10) e ligar pgvector.
4. Montar o wizard de onboarding (seção 7) e o primeiro sync dirigido.
5. n8n: agendar `sync_transferegov_ff` + `detect_changes`.
