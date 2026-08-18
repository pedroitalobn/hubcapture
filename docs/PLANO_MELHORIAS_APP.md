# Plano de melhorias do app — feedback "Alterações a serem feitas no APP"

> Origem: PDF de revisão do cliente (20 pontos, 9 páginas de prints anotados).
> **Ponto 02 desconsiderado por decisão do produto** (filtro de áreas do onboarding
> permanece como está).
> Execução em **duas fases**: primeiro o que é **UI/rótulo/layout** (rápido, sem tocar
> em ingestão), depois o que é **lógica/dados** (endpoints, connectors, migrations).

## Estado da execução

| Fase | Situação |
|---|---|
| **Fase 1 — interface** (§1.1 a §1.12) | ✅ entregue |
| **Fase 2 — 01 (excluir município)** | ✅ entregue |
| **Fase 2 — 20 (copiloto que não respondia)** | ✅ entregue (a central de demandas segue pendente) |
| **Fase 2 — 15 (pareceres)** | ✅ o elo proposta → plano de trabalho; falta **calibrar a rota contra a fonte viva** |
| **Fase 2 — 08/13 (“Publicado”)** | ✅ coletado nos dois sentidos (valor e estado); ver decisão 1 |
| **Fase 2 — 16 (emenda)** | 🔶 degradação e leitura da linha bruta do CSV; falta **calibrar a rota** |
| **Fase 2 — 03 (pesquisa falha)**, **11 (Oportunidades)**, **18 (Regularidade com dado)**, **19 (diretório institucional)**, **20b (central de demandas)** | ⏳ pendente |

**Bloqueio de ambiente:** a política de rede do ambiente de desenvolvimento remoto
recusa `CONNECT` para `*.gov.br`, então `probe_fontes` e `probe_especiais` não rodam
aqui. Tudo que depende de calibração contra a fonte viva (03, 11, 15 e 16 na parte de
rota) precisa de uma máquina com saída para gov.br — o código já está preparado, com
rota e parâmetro sobrescritíveis no painel admin.

---

## 0. Leitura geral do feedback

Os 20 pontos se separam em quatro naturezas:

| Natureza | Pontos | O que é |
|---|---|---|
| **Rótulo / texto** | 05, 06, 09 | trocar termo na interface — nenhum dado muda |
| **Layout / remoção** | 07, 13(parte), 14, 17, 04, 12, 03(parte) | tirar, mover ou acrescentar elemento já existente |
| **Dado novo / correção de coleta** | 08, 13(parte), 15, 16, 03(parte) | exige ingestão, calibração de rota ou campo novo |
| **Funcionalidade nova** | 01, 10, 11, 18, 19, 20 | endpoint, tela ou connector que ainda não existem |

Três pontos são **regressão de dado real em produção** e devem ser tratados com
prioridade dentro da Fase 2, porque hoje aparecem como mensagem de erro na cara do
gestor: **15** (pareceres), **16** (emenda parlamentar) e **03** (pesquisa falha em
Apuiarés/CE).

**Uma decisão precisa do cliente antes de codar** (ver §3): o que exatamente é
"**Publicado**" nos pontos 08 e 13 — um **valor em R$** (card financeiro, ao lado de
Empenhado e Pago) ou o **status de publicação** do convênio (o print do TransfereGov
mostra "Empenhado · Publicação · Publicado" como linha de *situação*, não de valor).
O plano assume **valor em R$ com queda para status** e sinaliza o ponto.

---

## FASE 1 — Interface (rótulos, layout, remoções)

Sem migration, sem connector. Tudo em `apps/web`, salvo dois campos de texto que nascem
no backend (`services/perfil.py`). Entrega em um PR único, revisável print a print.

### 1.1 · Ponto 06 — "Captação" vira "Propostas"
- **Onde**: `apps/web/app/panel/layout.tsx` (item `NAV`), `apps/web/app/panel/funding/page.tsx`
  (título), `apps/web/app/panel/funding/[id]/page.tsx:371` (breadcrumb "← Captação"),
  `apps/web/app/panel/page.tsx` (rótulo do feed "Captação"/"Recebido") e
  `apps/api/src/services/perfil.py:353` (`_dimensao("captacao", "Captação", …)` — o título do
  card vem do backend).
- **Não mudar**: a rota `/panel/funding`, a chave de módulo `captacao`, o valor `tipo="captacao"`
  do feed. §25 trava rotas em inglês e a chave é contrato de API/gate de plano.
- **Risco**: baixo. Buscar por `"Captação"` em `apps/web` e `apps/api/src/services` e trocar só
  o que é rótulo visível.

### 1.2 · Ponto 05 — "NOVA PROPOSTA" vira "NOVO ALERTA"
- **Onde**: `apps/web/app/panel/alerts/page.tsx:33` (`TIPO_LABEL`), `:58`, `:312` e
  `apps/web/components/DynamicIsland.tsx:86`.
- **Não mudar**: a chave `nova_proposta` (`services/oportunidades.py`, `models/alerta.py`) — é
  o tipo do alerta, usado no dedupe e no despacho por e-mail/WhatsApp.

### 1.3 · Ponto 09 — "Novidades de {ano} no seu território" vira "Propostas (filtro conforme o ano)"
- **Onde**: `apps/web/app/panel/page.tsx` (cabeçalho da seção do feed, ~linha 556).
- Ajustar também o texto de vazio logo abaixo, para não ficar "Nenhuma novidade…" sob um
  título que agora diz "Propostas".

### 1.4 · Ponto 07 — tirar "R$ X em propostas" do card Captação
- **Onde**: `apps/api/src/services/perfil.py:355` — o `destaque` da dimensão captação.
- **Como**: manter o campo `destaque` no schema (as outras dimensões usam), devolver `""`/`None`
  para captação; a UI (`app/panel/page.tsx`, `d.destaque ?? "—"`) passa a esconder a linha quando
  vazia em vez de imprimir "—".

### 1.5 · Ponto 08 — cards do Panorama financeiro: Total Geral · Empenhado · Publicado · Pago
- **Onde (UI)**: `apps/web/app/panel/page.tsx` (`PanoramaFinanceiro`).
- **Fase 1 entrega 3 dos 4**: *Total Geral* (= `cards.valor_conveniado`, renomeado),
  *Empenhado* (`cards.valor_empenhado` — **já existe** em `services/propostas.py:772` e nunca foi
  exibido) e *Pago* (novo no retorno, soma de `execucao.valor_pago`; o serviço já calcula `pago`
  internamente para o `valor_a_utilizar`).
- **Fase 2 entrega o 4º**: *Publicado* (§2.3).
- Saem da linha: "Desembolsado", "Em execução" e "Oportunidades abertas" — os dois últimos
  continuam disponíveis na tela de resumo da Captação (`/panel/funding/summary`).

### 1.6 · Ponto 13 (parte UI) — "Pago" sobe para a faixa de destaque; "Execução Financeira" sai
- **Onde**: `apps/web/app/panel/funding/[id]/page.tsx` — faixa `hero-band` (~484) e seção
  "Execução financeira — TransfereGov" (~657).
- **Como**: a faixa passa a ter **Valor total · Empenho · Pago · (Publicado, Fase 2)**; a seção
  inteira de execução financeira (barra empilhada + grade de 5 valores + vigências) é removida.
- **Atenção**: a seção removida é a única exibição de *Liberado*, *Saldo em conta*, *vigências* e
  *ente recebedor*. Recomendo preservar vigências/ente na grade "Dados gerais" para não perder a
  data de fim de vigência, que alimenta a leitura de prazo — **confirmar com o cliente**.
- **Também**: `services/pdf.py` desenha a mesma barra empilhada no espelho; alinhar o PDF à nova
  faixa na mesma passada (senão a tela e o documento divergem).

### 1.7 · Ponto 14 — tirar duas informações do cabeçalho do detalhe
- **Onde**: `apps/web/app/panel/funding/[id]/page.tsx:374-378` (linha `municipioSecundario(p)` =
  "IBGE 3502507") e `:428-431` (chip `{p.fonte}` = "TRANSFEREGOV_DISC").
- **Coerente com §19**: fonte de dados é detalhe de ingestão, não identidade de registro. O código
  IBGE segue disponível em "Dados gerais"; a fonte, no link "Fonte oficial ↗" e na proveniência.

### 1.8 · Ponto 17 — tirar os quadros "Acompanhar e ser avisado" e "Dados completos da fonte"
- **Onde**: `apps/web/app/panel/funding/[id]/page.tsx:817` e `:861` (+ `DadosCompletos`,
  `TextoExpansivel` e o estado `abrirTudo` ficam órfãos — remover import/estado junto).
- **Perda funcional a comunicar**: some o único ponto de "monitorar proposta-chave" do app. Proposta:
  virar um botão pequeno no grupo de ações do cabeçalho (junto de ★ Favoritar / Espelho PDF), que
  chama o mesmo `POST /monitors`. Custo baixo e nada se perde.

### 1.9 · Ponto 03 (parte UI) — filtro de ano sumindo
- **Causa**: `apps/web/app/panel/page.tsx` só desenha o seletor quando `anosDisponiveis.length > 1`.
  Em Apuiarés/CE o território tem uma única safra → o filtro simplesmente não aparece e lê-se como
  bug.
- **Correção**: desenhar sempre que houver ≥ 1 safra, desabilitado e rotulado ("safra única: 2026")
  quando só existe uma. A parte de *dados* ("a pesquisa está falha") é da Fase 2 (§2.1).

### 1.10 · Ponto 04 — botão "limpar pesquisa"
- **Onde**: `apps/web/app/panel/alerts/page.tsx` (formulário "Monitorar futuras propostas" +
  filtro "Só não lidos").
- **Como**: botão "Limpar" ao lado de "Monitorar" que devolve município/área/canais ao padrão e
  destrava o filtro da lista — mesma prática do "limpar tudo" já existente na Captação.

### 1.11 · Ponto 12 — "baixar no computador" no espelho PDF
- **Causa**: `apps/web/lib/api/client.ts:212` usa `navigator.canShare({files})`. No Chrome de
  **desktop** com celular vinculado isso é `true`, então abre a folha de compartilhamento do
  Android e o usuário perde o download.
- **Correção**: só usar `navigator.share` em ponteiro grosso (`matchMedia("(pointer: coarse)")`)
  ou expor as duas ações — `BotaoEspelho` com "Baixar" (padrão) e "Compartilhar" (secundário,
  quando `canShare` existe). Fallback de download permanece igual.

### 1.12 · Pontos 10 e 18 (casca) — itens "Oportunidades" e "Regularidade" no menu
- **Onde**: `apps/web/app/panel/layout.tsx` (`NAV`), páginas `app/panel/opportunities` e
  `app/panel/regularity`.
- **Fase 1**: entra a navegação e a página com o link oficial abrindo em nova aba —
  **Regularidade** → `https://cauc.tesouro.gov.br/ng/#/extrato/ente/filtro` (ponto 18) e
  **Oportunidades** → as duas consultas do TransfereGov (ponto 11), já com os filtros
  pré-preenchidos na URL quando a página JSF aceitar querystring.
- **Fase 2**: os dados dentro do Hub (§2.5 e §2.7).
- Ambos entram como **módulos** (`services/modulos.py::MODULOS`, §29) para ligar/desligar pelo
  painel admin sem redeploy.

**Saída da Fase 1**: 11 dos 19 pontos válidos fechados; nenhum toque em banco.

---

## FASE 2 — Lógica, dados e funcionalidades novas

Ordenada por dor do gestor: primeiro o que hoje aparece como erro na tela, depois o que falta.

### 2.1 · Ponto 03 — pesquisa falhando no município (Apuiarés/CE)
- **Diagnóstico**: rodar `python -m src.tools.probe_fontes <ibge> --json` da máquina com saída para
  gov.br (o sandbox de CI bloqueia). O print mostra 1 proposta com **R$ 0,00** — cheiro de
  `VL_GLOBAL_PROP`/`valor_total` não casados no de-para do connector, não de "município sem verba".
- **Onde olhar**: `connectors/transferegov_disc.py::_plano_do_csv` (casamento exato de coluna,
  §35b), `ingestion/normalizer.py::_ci` (alias de caixa — o CSV manda `NR_PROPOSTA` em maiúscula) e
  `services/propostas.valor_global_de`.
- **Também**: memória de tentativa da coleta (`services/consulta_avulsa`, §38) guarda "não achei
  nada" por 6 h — ao calibrar, limpar com `limpar_cache_coleta()`, senão o teste seguinte mente.

### 2.2 · Ponto 15 — os pareceres precisam aparecer
- **Causa exata** (a mensagem do print é o próprio diagnóstico): `services/pareceres.py:186` cai
  para `proposta.numero_proposta` quando `numero_plano_trabalho` está vazio, e
  `connectors/pareceres.py::id_do_plano` recusa "30011/2026" porque a rota
  `/planos_trabalho_analises_especiais` exige o **id inteiro** do plano. Nas propostas vindas do CSV
  (`transferegov_disc`) o nº do plano nunca é preenchido → nenhum parecer sai.
- **Correção (3 caminhos, nesta ordem)**:
  1. **Resolver o id do plano** a partir do `ID_PROPOSTA` que o CSV já traz (usado hoje só como
     `id_externo` em `transferegov_disc.py:200`): consultar a rota de planos de trabalho do módulo
     `especiais` por proposta, com a descoberta de rota+chave de `connectors/_especiais.py` (mesma
     mecânica do ponto 16) e gravar em `propostas.numero_plano_trabalho`.
  2. **Backfill** do que já está no cache (migration de dados, no molde de `c9d0e1f2a3b4`).
  3. **Scraping da tela de tramitação** como 2ª fonte (quem assinou): calibrar
     `pareceres_url_tramitacao`, hoje vazia por design.
- **Aceite**: a proposta 30011/2026 exibe os 3 pareceres de proposta + 5 do plano de trabalho que
  o print do TransfereGov mostra.

### 2.3 · Pontos 08 e 13 (dado) — "Publicado"
- **Pendente de decisão** (§3). Assumindo valor em R$:
  - coletar o campo na ingestão (`_montar_execucao` em `ingestion/normalizer.py`, chave
    `valor_publicado`/`publicacao`), somar em `services/propostas.resumo` e devolver em `cards`;
  - exibir no card do Panorama (§1.5) e na faixa do detalhe (§1.6).
- Se for **status** (Publicado/Não publicado), vira badge ao lado da Situação — muda o esforço de
  ~1 dia para ~2 h.

### 2.4 · Ponto 16 — emenda parlamentar e dados do programa
- **Causa**: `connectors/_especiais.py` exige duas evidências no OpenAPI (nome do assunto + chave
  aceita) e, não achando, o painel imprime o erro que aparece no print. Falta calibrar
  `emendas_esp_endpoint`/`emendas_esp_chave` contra a API viva.
- **Correção**:
  1. `python -m src.tools.probe_especiais --rotas` (máquina com saída para gov.br) → gravar os
     overrides no painel admin (Administração → Configurações → Fontes);
  2. acrescentar ao bloco os campos do print: **Valor da Emenda**, **comissão/tipo (INDIVIDUAL)**,
     **Solicitante(s)/Apoiador(es)** e os valores do programa (Global, Contrapartida, Repasse),
     vindos de `ListarProgramasPropostas/ProgramasDaPropostaDetalhar.do?id=…` — página JSF, então
     entra pelo facade de scraping (`scraping/scraper.py`) como 2ª fonte de verdade, com
     `proveniencia` por campo;
  3. enquanto a rota não responde, manter a degradação com conteúdo já existente
     (`emendas_do_registro_fonte`) em vez do texto de erro.

### 2.5 · Ponto 11 — Oportunidades: "Chamamento Público" e "Programas"
- **Novo connector** `connectors/transferegov_oportunidades.py` (Protocol de `base.py`), duas
  consultas do módulo voluntárias:
  - *Chamamento Público* — `…/prestacao/mrosc/ChamamentoPublico/chamamentoPublicoConsultaPesquisa.jsf`,
    filtros **Ano = ano corrente** e **Apto a receber proposta = Sim**;
  - *Programas* — `…/programa/ConsultarPrograma/ConsultarPrograma.do`, filtros **Qualificação do
    proponente = Proposta Voluntária**, **Ano = ano corrente**, **Apto a receber proposta = Sim**.
- **Importante**: o ano **não pode ser fixo em 2026** (o PDF é de 2026); vira parâmetro com padrão
  no ano corrente, mais override no painel admin.
- São páginas JSF com POST de formulário e paginação → `scraping/tabelas.py` + provider
  Playwright/Crawl4AI local; nada de novo na infra.
- **Ingestão**: são oportunidades abertas, não propostas do município — entram como `propostas` com
  `tipo=disponivel` (o classificador de §23 já separa) **ou** entidade própria `oportunidades`.
  Recomendo reusar `propostas` (menos superfície, filtros e favoritos de graça) com `fonte` própria.
- **Tela** `app/panel/opportunities` com as duas abas, filtros locais e ★ para favoritar.
- Maior item da fase — estimar sozinho (~3-5 dias) e validar a extração com `probe_fontes`.

### 2.6 · Ponto 01 — excluir município do perfil
- **Causa**: `services/onboarding.py:78` só faz `INSERT … ON CONFLICT DO NOTHING`. Não existe
  caminho de remoção; o único hoje é `DELETE /profile` (§41), que zera o perfil inteiro.
- **Backend**: `DELETE /api/v1/profile/municipalities/{ibge}` (`api/v1/perfil.py` +
  `services/perfil.remover_municipio`): apaga a linha de `municipios_interesse`, remove as
  `monitoramentos_busca` daquele IBGE, chama `consulta_avulsa.esquecer_municipio(ibge)` e registra
  `audit_log`.
- **Não apagar** propostas/repasses: são **cache global** compartilhado com outros tenants (§41) —
  a saída do território já os esconde via RLS.
- **UI**: "×" em cada chip do `components/TerritorioFiltro.tsx` com confirmação, e lista editável em
  `app/panel/account`. `lib/territorio.tsx` já poda IBGE que saiu do perfil.
- **Efeito colateral esperado**: `municipios_max` do plano volta a ter folga (§39).

### 2.7 · Ponto 18 — Regularidade (CAUC) com dado dentro do Hub
- A base já existe: módulo `conformidade` + connector `siconfi` + tela `app/panel/compliance`
  (desligados por padrão, §29).
- **Plano**: renomear a lente para **"Regularidade"** (rótulo, não chave), ligar o módulo, calibrar
  `siconfi_csv_url` e manter o link do extrato CAUC por ente como ação primária da tela.

### 2.8 · Ponto 19 — diretório institucional na Agenda de contatos
- Pedido: relação de **Gabinetes dos ministros**, **Chefias de Gabinete**, **Assessorias
  Parlamentares** e os **SEIs dos protocolos**.
- **Como**: contatos de **plataforma** (curados pelo admin), separados dos contatos pessoais do
  usuário — `contatos` hoje é dado por-tenant com RLS `FOR ALL` (§31). Duas opções:
  1. `contatos_institucionais` (tabela platform-level, sem RLS por-tenant) + aba "Institucionais"
     na agenda + CRUD/import `.vcf` no painel admin — **recomendada**;
  2. import `.vcf` na conta de cada usuário — mais barato, mas duplica e envelhece.
- O **SEI do protocolo** é campo novo (texto + link) — cabe em `detalhe`/`tags` sem migration se
  for pela opção 1 com jsonb.

### 2.9 · Ponto 20 — Copiloto não responde + central de demandas na Assessoria
- **Copiloto**: `app/panel/copilot/page.tsx` engole a falha (`try/finally` sem `catch`), então a
  tela fica muda — o usuário não sabe se é credencial, rede ou timeout. Correção em duas partes:
  1. superfície: mostrar o erro do SSE e o estado "sem credencial de IA configurada";
  2. causa: conferir `llm_*_api_key` em Administração → Configurações → IA e o diagnóstico de
     `GET /admin/sources`. Sem chave, `ai/chat.py` degrada — o Dynamic Island continua útil pelo
     roteador de fallback, mas a página de chat parece quebrada.
- **Central de demandas** (Assessoria): entidade `demandas` (por-tenant, RLS como `pastas`) com
  assunto, descrição, anexo opcional, status (`aberta|em_andamento|resolvida`) e histórico;
  endpoints `GET/POST /advisory/requests` + `PATCH` para o admin; tela nova em
  `app/panel/advisory` (aba "Minhas demandas") e fila no painel admin. Notificação por e-mail
  reusa `notifications/email.py`; WhatsApp reusa o Uniq (§17), ambos best-effort.

---

## 3. Decisões pendentes com o cliente

1. **"Publicado" (pontos 08 e 13)** — valor em R$ ou status de publicação? Muda o esforço e o lugar
   do elemento na tela.
2. **Ponto 17** — remover "Acompanhar e ser avisado" tira o único acesso a *monitorar
   proposta-chave*. Confirmar a proposta de virar botão no cabeçalho.
3. **Ponto 13** — remover "Execução financeira" também remove *Liberado*, *Saldo em conta*,
   *vigências* e *ente recebedor*. Confirmar se migram para "Dados gerais" ou saem de vez.
4. **Ponto 11** — as duas consultas de Oportunidades valem para **todos os municípios do
   território** ou são consulta nacional aberta (sem recorte)? O filtro do print não tem município.
5. **Ponto 19** — o diretório institucional é **igual para todos os clientes** (curadoria nossa) ou
   por assinatura?

---

## 4. Sequenciamento sugerido

| Fase | Conteúdo | Pré-requisito |
|---|---|---|
| **1** | §1.1 a §1.12 — rótulos, layout, remoções, casca de menu | nenhum |
| **2a** | §2.1, §2.2, §2.4 — regressões de dado visíveis na tela | máquina com saída para gov.br p/ `probe_fontes`/`probe_especiais` |
| **2b** | §2.6, §2.9 (copiloto), §2.3 | decisão 1 e 2 |
| **2c** | §2.5, §2.7, §2.8, §2.9 (central de demandas) | decisões 4 e 5 |

Cada fase entra como PR próprio, com teste onde há regra (`test_modulos.py`,
`test_calibracao_connectors.py`, `test_andamento.py` já cobrem os arredores dos pontos 15, 16 e das
telas de eixo).
