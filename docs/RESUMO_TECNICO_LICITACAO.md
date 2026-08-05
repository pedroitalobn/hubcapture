# Hub Capture — Resumo Técnico

**Documento de caracterização técnica da solução**
Destinação: instrução de processo licitatório / termo de referência
Versão do documento: 1.0

---

## 1. Identificação da solução

| Item | Descrição |
|---|---|
| **Denominação** | Hub Capture |
| **Categoria** | Plataforma SaaS (Software as a Service) de gestão de captação e acompanhamento de recursos públicos federais |
| **Natureza** | Sistema web multiusuário, com API pública versionada e aplicativo móvel previsto sobre o mesmo contrato |
| **Público-alvo** | Gestores públicos municipais, parlamentares, secretarias, gabinetes, consultorias e equipes técnicas de captação de recursos |
| **Modelo de acesso** | Navegador web (responsivo), com autenticação individual e controle de perfis; API REST documentada para integração |
| **Regime de operação** | Nuvem privada ou infraestrutura própria do contratante (containers Docker), sem dependência de provedor específico |

---

## 2. Problema que a solução resolve

Os recursos federais destinados aos municípios brasileiros — transferências voluntárias, fundo a fundo, transferências especiais, emendas parlamentares e repasses setoriais — estão distribuídos em **múltiplas plataformas oficiais distintas** (TransfereGov, Fundo Nacional de Saúde, FNDE, painéis do SERPRO, Portal da Transparência, Tesouro Nacional), cada uma com:

- interface, vocabulário e critérios de busca próprios;
- disponibilidade instável (indisponibilidades e erros intermitentes nas APIs oficiais);
- dados publicados com defasagem de um dia (D-1) e em formatos heterogêneos (API REST, CSV, páginas dinâmicas sem interface programática);
- ausência de qualquer visão consolidada por município.

**Consequência prática para a Administração:** o gestor não sabe, em um único lugar, (a) quais oportunidades de recurso estão abertas para o seu município, (b) quanto já foi empenhado e ainda não utilizado, (c) que prazos estão vencendo e (d) que pendências travam um convênio. O acompanhamento é feito por consulta manual, repetida, plataforma a plataforma — trabalho que consome horas de equipe técnica e, com frequência, resulta em perda de prazo e de recurso já disponibilizado.

### O que o Hub Capture entrega

| Dor identificada | Solução implementada |
|---|---|
| Dados dispersos em várias plataformas | Concentrador único: coleta automatizada, normalização em esquema canônico e visão consolidada por município |
| Instabilidade das fontes oficiais | Cache próprio ("cache-first"): a consulta do usuário responde do banco local; a ida à fonte é exceção, com política de novas tentativas, degradação controlada e registro de incidentes |
| Consulta manual e repetitiva | Sincronização agendada diária dos municípios monitorados + consulta sob demanda para municípios não monitorados |
| Perda de prazo e de recurso empenhado | Monitoramento ativo com detecção de mudança, alertas de prazo e destaque de **recurso empenhado ainda não utilizado** |
| Volume de informação técnica de difícil leitura | Camada de Inteligência Artificial: resumo automatizado das propostas e copiloto conversacional que responde sobre os dados do próprio território |
| Ausência de rastreabilidade do dado | Registro de **proveniência campo a campo** (qual fonte forneceu cada valor), trilha de auditoria e histórico de execuções de coleta |

---

## 3. Linguagens e tecnologias empregadas

### 3.1 Quadro-resumo (resposta direta)

| Camada | Linguagem | Tecnologia principal |
|---|---|---|
| **Front-end (interface web)** | **TypeScript / JavaScript (React)** | Next.js 15 · React 19 · Tailwind CSS 4 |
| **Back-end (API, regras de negócio, integrações, IA)** | **Python 3.12** | FastAPI · SQLAlchemy 2 (assíncrono) · Pydantic v2 |
| **Banco de dados** | **SQL (PostgreSQL)** | PostgreSQL 16 + extensão pgvector (busca vetorial/semântica) |
| **Infraestrutura / implantação** | — | Docker e Docker Compose (containers) |

### 3.2 Detalhamento por camada

#### Front-end — TypeScript

| Componente | Versão-alvo | Função |
|---|---|---|
| Next.js | 15.1 (App Router, modo *standalone*) | Framework de aplicação web, roteamento e renderização |
| React | 19 | Biblioteca de interface |
| TypeScript | 5.6 | Linguagem tipada (tipagem estrita; uso de `any` vedado por convenção interna) |
| Tailwind CSS | 4 | Sistema de estilos |
| openapi-typescript / openapi-fetch | 7.x / 0.13 | Cliente HTTP **tipado, gerado automaticamente** a partir do contrato OpenAPI da API |
| Node.js | ≥ 22 (execução) / 20 (imagem de build) | Ambiente de execução |
| pnpm + Turborepo | 10.33 / 2.5 | Gerenciador de pacotes e orquestração do monorepo |

O front-end é **exclusivamente camada de apresentação**: não acessa o banco de dados nem as fontes governamentais diretamente. Toda a regra de negócio reside no back-end, o que garante contrato único entre web e futuro aplicativo móvel.

#### Back-end — Python

| Componente | Versão-alvo | Função |
|---|---|---|
| Python | 3.12 | Linguagem da API, ingestão de dados e camada de IA |
| FastAPI | ≥ 0.115 | Framework da API REST; geração automática de especificação OpenAPI |
| Uvicorn | ≥ 0.32 | Servidor ASGI (execução assíncrona) |
| SQLAlchemy | 2.0 (modo assíncrono) + asyncpg | Mapeamento objeto-relacional e acesso ao banco |
| Alembic | ≥ 1.13 | Versionamento e migração de esquema de banco |
| Pydantic | v2 + Pydantic Settings | Validação de dados de entrada/saída e configuração |
| fastapi-users | ≥ 14 | Autenticação, cadastro, recuperação de senha e verificação de e-mail |
| httpx + tenacity | ≥ 0.27 / ≥ 9 | Cliente HTTP assíncrono com nova tentativa e recuo exponencial |
| LiteLLM | ≥ 1.50 | Camada de abstração multi-provedor de modelos de linguagem |
| pgvector (cliente) | ≥ 0.3 | Suporte a vetores para busca semântica |
| ReportLab | ≥ 4.2 | Geração de relatórios em PDF |
| Playwright / Crawl4AI | opcional (extra `scraping`) | Extração de dados de páginas oficiais que exigem execução de JavaScript |
| pytest, ruff, black | — | Testes automatizados, análise estática e formatação |

#### Banco de dados — PostgreSQL

| Componente | Versão | Função |
|---|---|---|
| PostgreSQL | 16 | Banco relacional principal |
| pgvector | 0.8 | Extensão de vetores — busca semântica sobre o acervo de propostas |
| Row Level Security (RLS) | nativo do PostgreSQL | **Isolamento multiusuário aplicado no próprio banco** (ver seção 7) |

Estrutura atual: **23 tabelas**, governadas por **12 migrações versionadas** em Alembic. Alterações de esquema são obrigatoriamente versionadas — não há alteração manual de estrutura.

#### Componentes complementares

| Componente | Função | Caráter |
|---|---|---|
| Redis + ARQ | Fila de processamento para sincronizações pesadas | Previsto na arquitetura |
| n8n | Orquestração de rotinas agendadas (sincronização diária, detecção de mudanças, disparo de alertas) | Perfil opcional do ambiente |
| SMTP | E-mail transacional (convite, recuperação de senha, alertas) | Opcional — degrada sem interromper o fluxo |
| Provedores de IA (Anthropic, OpenAI, Google, DeepSeek, xAI, Moonshot, Alibaba, Z.ai) | Resumo, copiloto e busca semântica | Opcional e intercambiável — a plataforma opera sem IA |
| Uniq.chat (WhatsApp) | Alertas e chat por WhatsApp | Opcional |

**Nota de arquitetura relevante para contratação:** todos os provedores externos pagos (IA, extração web, WhatsApp, e-mail) são **opcionais e substituíveis**, configurados em tempo de execução por painel administrativo. Na ausência de credencial, o recurso é desativado com degradação elegante e a plataforma **continua entregando os dados**. Não há dependência de fornecedor único (*vendor lock-in*).

---

## 4. Arquitetura da solução

```
┌──────────────────────────────────────────────────────────────┐
│  CLIENTES                                                     │
│  Web (Next.js/React)   ·   Aplicativo móvel (previsto)        │
└───────────────────────────┬──────────────────────────────────┘
                            │  mesmo contrato REST · autenticação por token
┌───────────────────────────▼──────────────────────────────────┐
│  API PÚBLICA v1 — FastAPI (Python)                            │
│  /api/v1/... · OpenAPI · JWT · isolamento por usuário (RLS)   │
└───────────────────────────┬──────────────────────────────────┘
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐ ┌────────▼────────┐ ┌────────▼─────────────┐
│ MOTOR DE DADOS │ │ CAMADA DE IA    │ │ CAMADA DE INGESTÃO   │
│ normalização   │ │ resumo·copiloto │ │ conectores plugáveis │
│ deduplicação   │ │ busca semântica │ │ API + extração web   │
│ detecção de    │ │ (opcional)      │ │ nova tentativa,      │
│ mudança·hash   │ │                 │ │ fallback, incidentes │
└───────┬────────┘ └─────────────────┘ └────────┬─────────────┘
        │                                        │
        ▼                                        ▼
┌──────────────────────────────┐   ┌───────────────────────────┐
│ PERSISTÊNCIA                 │   │ FONTES OFICIAIS           │
│ PostgreSQL 16 + pgvector     │   │ TransfereGov · FNS · FNDE │
│ 23 tabelas · RLS por usuário │   │ SERPRO · Tesouro · Portal │
└──────────────────────────────┘   │ da Transparência · IBGE   │
                                   └───────────────────────────┘
     ORQUESTRAÇÃO (n8n) → sincronização diária · detecção de
     mudanças · disparo de alertas → e-mail / painel / WhatsApp
```

### Princípios arquiteturais adotados

| Princípio | Decisão de projeto | Benefício para o contratante |
|---|---|---|
| **API única e versionada** | Uma API REST v1 atende web e móvel, com contrato OpenAPI publicado | Integração com sistemas de terceiros e evolução sem quebra de contrato |
| **Cache próprio ("cache-first")** | A leitura do usuário responde do banco local; a ida à fonte é exceção | Resposta rápida e resiliência à indisponibilidade das fontes oficiais |
| **Conectores plugáveis** | Cada fonte é um módulo isolado que implementa a mesma interface | Inclusão de nova fonte não exige reescrita do sistema |
| **Coleta combinada** | API oficial e extração de página rodam em paralelo e são fundidas com regra de precedência declarada | Dado mais completo e mais atual do que qualquer fonte isolada |
| **Normalização canônica** | Toda fonte converge para um esquema único | Visão consolidada e comparável entre programas |
| **IA como camada, não como acoplamento** | Recursos de IA são serviços desacopláveis | Falha ou ausência de provedor de IA não interrompe a operação |
| **Isolamento no banco** | Segurança multiusuário aplicada por política do PostgreSQL, não apenas por código de aplicação | Vazamento entre usuários é barrado pelo próprio banco |
| **Modularidade operacional** | Cada eixo funcional pode ser ligado/desligado em tempo de execução por painel administrativo | Implantação faseada, sem nova versão e sem interrupção |

---

## 5. Funcionalidades da plataforma

A navegação é **orientada ao perfil do usuário** (município(s) de interesse, áreas de atuação e papel), e não à fonte de dados. As plataformas governamentais são detalhe técnico de ingestão, nunca item de menu.

### 5.1 Cadastro, onboarding e perfil

- Autocadastro, cadastro por convite e criação por administrador.
- **Onboarding conversacional**: assistente em formato de diálogo que captura papel do usuário, município(s) — com busca por nome via base oficial do IBGE ou código IBGE de 7 dígitos —, áreas de interesse, fontes e canais de alerta.
- Disparo automático da **primeira sincronização real** ao concluir o cadastro, cobrindo todos os eixos habilitados, com execução assíncrona e registro por fonte.
- Gestão de conta pelo próprio usuário: dados pessoais, telefone, adesão a notificações e alteração de senha.
- Recuperação de senha e verificação de e-mail por link com token.

### 5.2 Eixo Captação — propostas, editais e programas

- Listagem consolidada das oportunidades do território, com **busca em tempo real** nas fontes (a consulta é disparada a cada alteração de filtro, com controle de concorrência e supressão de resposta obsoleta).
- Classificação automática entre **oportunidade disponível** e **proposta já cadastrada**.
- Filtros de granularidade equivalente às plataformas de referência do mercado: busca livre, modalidade/instrumento, órgão, situação, **natureza jurídica do proponente**, qualificação, exercício, faixa de valor, área e ordenação (recentes, prazo, nome, órgão, valor). Filtros ativos são exibidos e removíveis individualmente.
- **Facetas dinâmicas**: cada filtro apresenta apenas as opções existentes no recorte, com contagem.
- **Execução financeira do TransfereGov**: valor global, empenhado, liberado, pago e saldo em conta, com destaque para **"empenhado a utilizar"** — recurso já disponibilizado ao município e ainda não executado.
- Página de detalhe estruturada: dados gerais, valores, situação, prazos, pendências, execução financeira com barra de progresso e **proveniência do dado**.
- Painel de resumo com séries por exercício (aprovado × desembolsado), pipeline por situação e convênios vigentes com percentual de desembolso.
- Favoritos (aba de acompanhamento), pastas de organização com cor e agrupamento livre.
- Exportação de relatório em CSV (compatível com Excel) do recorte exibido em tela e exportação de proposta em PDF.
- Consulta de **prazos a vencer** em janela configurável.

### 5.3 Eixo Recursos Recebidos

- Consolidação de repasses efetivamente recebidos pelo município, com decomposição entre crédito, dedução e repasse líquido.
- Visão geral com totalizadores, série histórica e feed cronológico.
- **Emendas parlamentares** como lente analítica: valores empenhado/pago e percentual executado, evolução anual, distribuição por modalidade e por área/função, ranking de parlamentares e listagem detalhada, com exportação em CSV.

### 5.4 Eixo Conformidade Fiscal *(implementado — desativado por padrão)*

- Situação de conformidade do município (CAUC) e capacidade de pagamento (CAPAG), com indicadores por status e por seção.

### 5.5 Eixo Obras *(implementado — desativado por padrão)*

- Acompanhamento de execução de obras: situação, percentual de execução, valor de investimento e valor repassado, datas e georreferenciamento, com visualização em mapa.

### 5.6 Monitoramento e alertas

- Monitoramento de proposta específica, com escolha de canais (painel, e-mail, WhatsApp).
- **Monitoramento de oportunidades futuras**: vigilância sobre município (com recorte opcional por área ou fonte), que alerta quando surge algo novo.
- **Detecção de mudança** por comparação de assinatura de conteúdo (*hash*), com registro do estado anterior e posterior.
- Varredura de oportunidades que identifica, entre outros, o cenário de **"recurso disponível no município sem proposta cadastrada"**.
- Central de alertas com marcação de leitura e disparo por e-mail e WhatsApp conforme os canais escolhidos.

### 5.7 Inteligência Artificial

- **Resumo automatizado** das propostas, gerado no processo de ingestão (em lote, não no clique do usuário) e adaptado ao papel do gestor.
- **Copiloto conversacional** em duas modalidades: chat sobre a base de conhecimento normativa e chat sobre os dados do próprio território, com resposta em fluxo contínuo (*streaming*).
- **Copiloto persistente em "ilha dinâmica"**: componente flutuante disponível em todas as telas do painel, que executa consultas reais aos serviços da plataforma (visão geral de repasses, listagem de propostas, prazos, conformidade, obras, notícias e busca semântica) dentro da mesma sessão de segurança do usuário — o agente enxerga exclusivamente o território do próprio usuário, por construção.
- **Busca semântica** sobre o acervo de propostas, com uso de vetores (pgvector) e alternativa textual quando não há provedor de IA configurado.
- **Operação sem IA**: na ausência de credencial, um roteador determinístico por palavra-chave executa a consulta mais provável e formata resposta legível.

### 5.8 Agenda de contatos com sincronização bidirecional

- Agenda de pessoas do gestor (gabinetes, secretarias, técnicos, fornecedores) integrada à plataforma.
- **Sincronização nos dois sentidos** com Google Contacts (People API), Microsoft/Outlook (Graph) e Apple/iCloud ou servidores CardDAV genéricos, com sincronização incremental por *delta token*.
- Resolução de conflito por comparação de três assinaturas (local, remota e última sincronizada); quando ambos os lados mudam, os registros são **fundidos sem perda** de e-mails, telefones ou marcadores.
- Importação e exportação em formato vCard (.vcf) como via manual independente de provedor.

### 5.9 Administração da plataforma

- **Gestão de usuários**: criação, edição de papel, plano, permissão administrativa e status; exclusão.
- **Convites**: emissão com papel, plano e prazo de validade; envio por e-mail e link de aceite.
- **Planos**: catálogo configurável com preço e limites; enforcement do limite de municípios no onboarding.
- **Módulos**: liga/desliga de cada eixo funcional em tempo de execução, sem nova implantação. Eixo desativado deixa de existir para a API (resposta 404) e desaparece do menu.
- **Configuração de provedores**: credenciais e endereços de todas as integrações administrados por painel, agrupados por categoria (IA, extração web, fontes, WhatsApp, e-mail, integrações). Segredos são armazenados cifrados e exibidos mascarados.
- **Diagnóstico de fontes**: verificação de saúde ao vivo de todos os conectores em paralelo, com última coleta bem-sucedida por fonte e estado de cada provedor.
- **Multi-provedor de IA**: ao cadastrar a chave de um provedor, os modelos disponíveis são listados ao vivo a partir do próprio provedor.

---

## 6. Integração com as fontes oficiais

### 6.1 Conectores implementados

Treze conectores, todos aderentes à mesma interface programática, com nova tentativa e recuo exponencial compartilhados:

| Conector | Fonte oficial | Eixo |
|---|---|---|
| `transferegov_ff` | TransfereGov — Fundo a Fundo | Captação |
| `transferegov_esp` | TransfereGov — Transferências Especiais | Captação |
| `transferegov_voluntarias` | TransfereGov — Transferências Voluntárias | Captação |
| `transferegov_disc` | TransfereGov — Discricionárias e Legais (CSV oficial) | Captação |
| `serpro` | Painel público da Visão Geral do TransfereGov | Captação |
| `fns` | Fundo Nacional de Saúde | Recebidos |
| `fnde` | Fundo Nacional de Desenvolvimento da Educação | Captação |
| `fpm` | Fundo de Participação dos Municípios (Tesouro Nacional) | Recebidos |
| `emendas` | Emendas parlamentares (Portal da Transparência) | Recebidos |
| `siconfi` | Siconfi / CAUC / CAPAG (Tesouro Nacional) | Conformidade |
| `sismob` | SISMOB — obras de saúde | Obras |
| `simec` | SIMEC — obras de educação | Obras |
| `caixa` | CAIXA/SIORB — obras de infraestrutura | Obras |

**Escopo em operação na versão atual:** TransfereGov (cinco conectores) e FNS. Os demais permanecem implementados, registrados e cobertos por testes no repositório, aguardando calibração final contra as APIs em produção. A reativação de qualquer fonte é uma alteração de configuração — o núcleo do sistema não muda.

### 6.2 Estratégia de coleta

- **Coleta combinada:** API oficial e extração de página são executadas **em paralelo** e os registros são pareados e fundidos. Precedência declarada: a **API prevalece** em identificadores, valores e datas; a **extração prevalece** em situação, pendências e última movimentação (dado mais atual, pois a API oficial publica com defasagem D-1). Registro que existe apenas na página pública entra igualmente no acervo.
- **Proveniência:** cada campo do registro consolidado grava a origem do valor, permitindo auditoria completa da fusão.
- **Conectores autocalibráveis:** rotas e nomes de colunas das APIs oficiais são descobertos em tempo de execução (via especificação OpenAPI do próprio serviço ou catálogo de metadados), com possibilidade de sobrescrita manual pelo painel administrativo. Isso absorve mudanças das fontes sem nova implantação.
- **Extração local:** navegador headless executado no próprio container, sem dependência de serviço externo pago, para as páginas oficiais que só renderizam com JavaScript. Extração determinística de tabelas e grades ARIA, sem custo por página.
- **Registro de incidentes:** toda falha de fonte é registrada em tabela operacional com status (`ok` / `degradado` / `erro`), quantidade de registros e mensagem. Falha nunca é silenciosa e falha de uma fonte não interrompe as demais.
- **Ferramenta de diagnóstico:** utilitário de linha de comando que consulta as fontes reais e relata, por fonte, se respondeu, quantos registros retornaram e quais campos vieram — sem necessidade de banco ou da API em execução.

---

## 7. Segurança e proteção de dados

| Controle | Implementação |
|---|---|
| **Autenticação** | Token JWT com par de acesso (validade padrão de 15 minutos) e renovação (14 dias); senhas armazenadas com hash |
| **Isolamento multiusuário** | **Row Level Security nativo do PostgreSQL**. A aplicação conecta com papel de banco **não-superusuário** (superusuário ignora políticas e produziria segurança aparente); o inquilino é definido por requisição com escopo de transação, jamais de forma global — sem vazamento entre requisições do pool de conexões |
| **Reforço de política** | `FORCE ROW LEVEL SECURITY` aplicado inclusive ao proprietário das tabelas, evitando falso resultado positivo em auditoria |
| **Política restritiva por omissão** | Sem inquilino definido, a política **nega tudo** |
| **Separação de privilégios** | Migrações executam com papel proprietário; o tempo de execução usa exclusivamente o papel de aplicação restrito |
| **Segredos em repouso** | Credenciais de provedores e de integrações cifradas com Fernet (chave dedicada), exibidas mascaradas na leitura |
| **Guarda de segredo no boot** | Em ambiente produtivo, a inicialização é **abortada** se os segredos de token permanecerem com valor padrão, com instrução explícita de correção |
| **Trilha de auditoria** | Tabela de auditoria por usuário (ação, entidade, data/hora) e histórico completo de execuções de coleta |
| **Privacidade (LGPD)** | Mascaramento de dados bancários conforme o papel do usuário; dados pessoais da agenda de contatos são de escopo estritamente individual, com política de isolamento total; credenciais de integração cifradas; exclusão lógica com propagação da remoção às agendas conectadas |
| **Não divulgação de existência de conta** | Os fluxos de recuperação de senha nunca revelam se um e-mail está cadastrado |
| **Controle de acesso administrativo** | Perfil de superusuário exigido nas rotas administrativas, verificado por dependência dedicada |
| **Superfície de exposição** | Na configuração de implantação recomendada, apenas a aplicação web é exposta publicamente; a API é alcançada por *proxy* de mesma origem através da rede interna, dispensando domínio público próprio |

Cobertura de testes automatizados inclui verificação específica das políticas de isolamento (executadas com o papel de aplicação, e não com o proprietário, para que a asserção seja válida).

---

## 8. Modelo de dados

**23 tabelas** organizadas em quatro grupos:

| Grupo | Tabelas | Política de acesso |
|---|---|---|
| **Identidade e plataforma** | `usuarios`, `planos`, `convites`, `configuracoes`, `base_conhecimento` | Nível de plataforma |
| **Dados do usuário (isolamento total)** | `municipios_interesse`, `preferencias_usuario`, `favoritos`, `pastas`, `pasta_propostas`, `monitoramentos`, `monitoramentos_busca`, `alertas`, `audit_log`, `contatos`, `integracoes_contatos`, `contato_vinculos` | RLS para todas as operações, por usuário |
| **Acervo público (cache compartilhado)** | `propostas`, `proposta_embeddings`, `repasses`, `conformidades`, `obras` | RLS restringindo a leitura aos municípios de interesse do usuário |
| **Operacional** | `sync_runs` | Registro de execuções e incidentes de coleta |

**Chave canônica de território:** código IBGE do município (7 dígitos). Todo mapeamento entre fontes converge para essa chave.

Entidades canônicas do ciclo completo do recurso — **captar → receber → executar → prestar contas**: `proposta` (captação), `repasse` (recebidos), `conformidade` (fiscal) e `obra` (execução).

---

## 9. Interface programática (API)

- **Mais de 90 endpoints REST** sob o prefixo `/api/v1`, com rotas padronizadas em inglês e vocabulário de domínio em português.
- **Especificação OpenAPI** publicada em `/api/v1/openapi.json` e documentação interativa em `/api/v1/docs`.
- **Cliente tipado gerado automaticamente** a partir da especificação, consumido pela aplicação web e reaproveitável por aplicativo móvel ou por sistemas de terceiros.
- Todas as respostas validadas por esquemas tipados; todas as rotas autenticadas aplicam o isolamento por usuário.
- Recursos de resposta em fluxo contínuo (SSE) para o copiloto.
- Endpoint de verificação de saúde (`/health`) para sondagem por orquestrador.

Agrupamento funcional: autenticação e conta · perfil e território · municípios · propostas (listagem, detalhe, busca ao vivo, facetas, resumo, prazos, relatório, PDF) · repasses e emendas · conformidade · obras · onboarding · favoritos · pastas · contatos e integrações · monitoramentos · alertas · notícias · planos · copiloto · administração (usuários, convites, configuração, fontes, módulos) · webhooks.

---

## 10. Implantação e requisitos de infraestrutura

### 10.1 Modelo de implantação

Implantação por **containers Docker**, orquestrada por Docker Compose, com um único comando de subida. Compatível com plataformas de implantação baseadas em *proxy* reverso (Traefik/Dokploy) e com qualquer provedor de nuvem ou servidor próprio do contratante.

| Serviço | Conteúdo | Observação |
|---|---|---|
| `postgres` | PostgreSQL 16 com pgvector | Volume persistente; verificação de saúde |
| `api` | API FastAPI | Aguarda o banco, aplica as migrações automaticamente e inicia; verificação de saúde por endpoint |
| `web` | Aplicação Next.js (modo *standalone*) | Faz *proxy* de mesma origem para a API pela rede interna |
| `redis` | Fila de processamento | Suporte a cargas assíncronas |
| `n8n` | Orquestração de rotinas agendadas | Perfil opcional |

Características operacionais:

- **Migrações automáticas** na inicialização do container da API — sem passo manual de banco.
- **Provisionamento do administrador inicial** na inicialização, de forma idempotente, com nova tentativa e autorreparo no login — destrava o primeiro acesso sem carga manual de dados.
- **Criação automática dos planos padrão** na primeira execução.
- **Verificações de saúde** em todos os serviços críticos, evitando encaminhamento de tráfego para instância ainda não pronta durante janelas de atualização.
- **Sem publicação de portas fixas** na configuração de produção, evitando conflito em ambientes compartilhados.
- Imagem enxuta opcional (sem navegador headless) por parâmetro de construção, para cenários que dispensem extração de páginas dinâmicas.

### 10.2 Requisitos mínimos de ambiente

| Item | Requisito |
|---|---|
| Sistema operacional | Linux com Docker Engine e Docker Compose |
| Recursos | Ambiente de container com suporte a PostgreSQL 16 e navegador headless (aproximadamente 500 MB adicionais de imagem quando a extração de páginas está habilitada) |
| Rede | Saída HTTPS para as fontes oficiais do governo federal |
| Persistência | Volume para o banco de dados |
| Configuração | Arquivo de variáveis de ambiente; demais credenciais administráveis por painel em tempo de execução |
| Dependências externas obrigatórias | **Nenhuma** — provedores de IA, extração paga, WhatsApp e e-mail são todos opcionais |

---

## 11. Qualidade, manutenção e evolução

| Aspecto | Situação |
|---|---|
| **Testes automatizados** | **169 testes** (pytest) cobrindo normalização, fusão de fontes, cache, políticas de isolamento, conectores, calibração, autenticação, planos, módulos, copiloto, busca semântica, contatos e sincronização, filtros de captação, obras, conformidade, PDF e WhatsApp |
| **Padronização de código** | Análise estática (ruff), formatação automática (black) no back-end; ESLint e Prettier com tipagem estrita no front-end; anotação de tipos obrigatória em Python |
| **Versionamento de banco** | Alembic — 12 migrações versionadas; alteração manual de esquema vedada |
| **Volume de código** | Aproximadamente 20.500 linhas de Python e 15.500 linhas de TypeScript/TSX (excluídas dependências) |
| **Documentação técnica** | Documento de arquitetura detalhado e blueprint de execução mantidos no repositório; especificação OpenAPI gerada automaticamente |
| **Extensibilidade** | Nova fonte de dados = novo módulo conector aderente à interface comum + mapeamento no normalizador da entidade-alvo. O núcleo não é alterado e **nenhuma fonte vira item de menu** |
| **Controle de versão** | Repositório Git com histórico e convenção de mensagens de commit |

---

## 12. Estado de maturidade por módulo

| Módulo | Implementação | Estado padrão na versão atual |
|---|---|---|
| Captação (propostas, editais, execução financeira) | Completa | **Ativo** |
| Copiloto e IA | Completa | **Ativo** |
| Agenda de contatos com sincronização | Completa | **Ativo** |
| Recursos recebidos (repasses, emendas) | Completa | Desativado (foco de validação na Captação) |
| Conformidade fiscal (CAUC/CAPAG) | Completa | Desativado — aguarda calibração da fonte |
| Obras (SISMOB/SIMEC/CAIXA) | Completa | Desativado — aguarda calibração da fonte |
| Aplicativo móvel (Expo/React Native) | Estrutura preparada; consome a mesma API v1 | Fase 2 |

A ativação de qualquer módulo é operação de painel administrativo, sem nova versão do software e sem interrupção do serviço.

---

## 13. Síntese executiva

O Hub Capture é uma **plataforma web multiusuário** que concentra, normaliza e monitora recursos federais destinados aos municípios brasileiros, cobrindo o ciclo completo **captar → receber → executar → prestar contas**.

- **Front-end:** TypeScript com Next.js 15 e React 19.
- **Back-end:** Python 3.12 com FastAPI, SQLAlchemy 2 assíncrono e Pydantic v2.
- **Banco de dados:** PostgreSQL 16 com extensão pgvector.
- **Implantação:** containers Docker, em infraestrutura própria do contratante ou em nuvem, sem dependência de provedor específico.

Diferenciais técnicos com efeito direto na contratação: isolamento de dados aplicado no próprio banco de dados (Row Level Security); cache próprio que garante disponibilidade mesmo com as fontes oficiais instáveis; conectores plugáveis e autocalibráveis que absorvem mudanças das plataformas governamentais sem nova implantação; rastreabilidade campo a campo da origem de cada dado; e ausência total de dependência obrigatória de serviços pagos de terceiros.
