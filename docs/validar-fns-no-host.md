# Prompt de contexto — validar o FNS (e as demais fontes) dentro do host

O sandbox do agente remoto **bloqueia `*.gov.br` no egress** (CONNECT 403), então
"a fonte está funcional?" só pode ser respondido de uma máquina com saída para a
internet — a sua. Este arquivo É o prompt: copie do `---` até o fim e cole numa
sessão do Claude Code aberta na raiz do repositório, no seu host.

Calibrar connector é trabalho **empírico** (§27 do CLAUDE.md): a rota oficial e os
nomes de coluna divergem do chute estático, e só a resposta real diz qual é qual.
O prompt abaixo carrega esse contexto para a sessão local não precisar redescobrir
a arquitetura antes de agir.

---

## Missão

Validar contra a fonte VIVA se a integração do connector `fns` (Fundo Nacional de
Saúde, portal ConsultaFNS) está funcional e, se não estiver, **calibrar** rota e
mapeamento de campos até estar. Trabalhe no repositório `hubcapture`, a partir da
raiz.

## O que você precisa saber antes de agir

Leia `CLAUDE.md` §5 (coleta combinada), §27 (connectors autocalibráveis), §30
(recorte de duas fontes + scraping como 2ª fonte de verdade) e §30b (FNS API-first).
Resumo operacional:

- `apps/api/src/connectors/fns.py` roda **API e scraping em paralelo**. A API do
  ConsultaFNS é a fonte primária; o scraping da página é a 2ª fonte de verdade. Os
  dois lados pareiam pela **portaria/OB** (comparação só por dígitos) e fundem: API
  vence em id/valor/data/documento, scraping vence em `descricao`/`categoria`. A
  origem de cada campo vai para `proveniencia` (via `raw["_proveniencia"]`).
- A **rota do backend não é fixa**. A ordem de resolução é: override
  `fns_api_endpoint` (painel admin ou `.env`) → cache em memória → `ENDPOINT_CANDIDATES`
  no topo de `fns.py`. Calibrar = descobrir a rota real e gravá-la.
- Os **parâmetros** vão nos dois estilos conhecidos (código de município de 6 dígitos
  e IBGE de 7). Quando a resposta ecoa alguma coluna de IBGE/município, há refiltro
  estrito no cliente — linha de outro município **nunca** entra.
- O casamento de coluna é por palavra-chave com normalização camelCase→snake
  (`vlRepasse` → `vl_repasse`), cobrindo camelCase, snake_case e CAIXA ALTA.

Pontos de calibração, todos em `apps/api/src/connectors/fns.py`:
`ENDPOINT_CANDIDATES` (rotas) · `_CHAVES_LISTA` (onde a resposta embrulha as linhas)
· `_montar_raw` (palavras-chave de cada campo) · `_linha_do_municipio` (refiltro) ·
`EXTRACT_SCHEMA` (o que o scraper estrutura da página).

Chaves de configuração (categoria `fonte` no painel admin, ou `.env`):
`fns_api_url` (default `https://consultafns.saude.gov.br/recursos/`),
`fns_api_endpoint` (vazio = candidatos), `fns_consulta_url` (a página, para scraping).

## Protocolo

Execute nesta ordem e **mostre a saída real** de cada passo — não resuma para
"funcionou".

1. **Preparar** (não precisa de banco nem da API no ar):
   ```bash
   cd apps/api && uv sync
   ```

2. **Probe da fonte** — é o diagnóstico bruto (rota, nº de registros, campos reais):
   ```bash
   uv run python -m src.tools.probe_fontes 3550308 --fonte fns
   ```
   Rode também com um município do seu interesse real (ex.: `2611606` Recife).
   `--json` serve para guardar a saída.

3. **Teste ao vivo com asserção** — mesmo diagnóstico, com exit code:
   ```bash
   LIVE_FONTES=fns uv run pytest tests_live/ -q -s
   ```
   Aprova só com `health_check` True **e** ≥1 registro coletado. Knobs:
   `LIVE_IBGE`, `LIVE_DIAS`, `LIVE_TIMEOUT`.

4. **Suíte normal** (garante que a calibração não quebrou o resto). Precisa do
   Postgres do compose de pé:
   ```bash
   docker compose up -d postgres
   uv run alembic upgrade head && uv run pytest -q
   ```

## Como interpretar o resultado (e o que fazer em cada caso)

- **`status: ok` com registros** → a integração está funcional. Confira na amostra
  se `valor`, `data_repasse`, `documento` e `descricao` vieram preenchidos e
  coerentes. Campo vazio significa palavra-chave não casada em `_montar_raw`:
  acrescente a palavra observada na resposta real e rode o probe de novo.

- **`403 Forbidden` / `401`** → o backend exige cabeçalho de navegador, cookie de
  sessão ou `Referer` do portal. Descubra o que o portal envia de verdade (DevTools
  → aba Network → a chamada XHR da consulta → "Copy as cURL"), reproduza a chamada
  no terminal, e só então ajuste o connector (o `_http.get_json` aceita `headers`).
  Cole no relatório o cURL real que funcionou.

- **`404` em todos os candidatos** → a rota mudou. Pegue o caminho verdadeiro na
  mesma aba Network, grave em `fns_api_endpoint` (painel admin `/admin/config`,
  categoria fonte, ou `.env`) e confirme com o probe. Se a rota for estável,
  acrescente-a a `ENDPOINT_CANDIDATES` para nascer calibrada em qualquer instalação.

- **"nenhuma linha do município"** → respondeu, mas o refiltro descartou tudo.
  Verifique como a resposta nomeia a coluna de município e ajuste
  `_linha_do_municipio` / os parâmetros enviados. **Nunca** relaxe o refiltro a
  ponto de aceitar linha de outro município: pior que fonte vazia é ingerir o
  Brasil inteiro como se fosse do município.

- **Município realmente sem repasse no período** → aumente a janela
  (`--dias 730`) e teste uma capital antes de concluir. Vazio numa capital é
  sintoma, não normalidade.

- **Scraping (2ª fonte) não roda** → é opcional e degrada sozinho. Para ligar
  localmente: `uv sync --extra scraping && uv run playwright install chromium`, e
  no painel admin (categoria scraping) ligue `scraping_playwright=on` ou
  `scraping_crawl4ai_local=on`. A API sozinha já deve entregar dados; o scraping
  acrescenta os descritivos.

## Regras de execução

- **Não reabra decisões travadas** do CLAUDE.md (API-first, profile-centric, rotas
  em inglês, recorte de duas fontes). Fonte nova nunca vira aba de menu.
- Mudou o comportamento do connector? Cubra com teste em
  `apps/api/tests/test_calibracao_connectors.py` (seção FNS), com a resposta real
  como fixture — é o que impede a regressão na próxima mudança da fonte.
- Rode `uv run ruff check src/ tests/` e `uv run black src/ tests/` antes de commitar.
- Commits convencionais. Branch de trabalho: `claude/fns-api-integration-4hg1ej`
  (ou uma nova a partir de `main`, se aquela já tiver sido mergeada).
- **Erro de fonte nunca é engolido**: precisa aparecer em `sync_runs` e na tela com
  mensagem explícita. "Não consegui abrir a página" jamais pode virar "a fonte não
  tem registros" — o gestor leria painel vazio como verdade.

## O que me devolver

1. Veredito por município testado: **funcional** ou **não funcional**, com a saída
   do probe colada.
2. Se calibrou: a rota real, os nomes de coluna reais e o diff do que mudou.
3. Se travou em autenticação: o cURL real da chamada do portal (sem cookies de
   sessão pessoal no texto — troque por `<REDACTED>`).
4. O estado da suíte (`uv run pytest -q`) depois das mudanças.
