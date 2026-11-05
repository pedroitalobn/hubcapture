# API de integração do Hub Capture — guia do parceiro e da operação

Este documento tem duas partes:

1. **Para o parceiro** (quem integra um sistema): como autenticar, quais são os
   limites, o que a API devolve e como testar no sandbox.
2. **Para a operação** (quem administra o Hub): como subir o sandbox no Dokploy,
   como liberar a API num plano e como emitir e revogar chaves.

---

## Parte 1 — Para o parceiro

### Ambientes

| Ambiente | Endereço | Chave | Dados |
|---|---|---|---|
| **Sandbox** (testes) | `https://sandbox.<domínio>/api/v1` | `hub_test_…` | fictícios, recriados todo dia |
| **Produção** | `https://<domínio>/api/v1` | `hub_live_…` | reais, do território da conta |

Uma chave só vale no ambiente dela. Chave `hub_live_` no sandbox (ou o
contrário) responde `401 API_CHAVE_AMBIENTE_ERRADO`.

### Autenticação

Envie a chave em todo pedido, no cabeçalho `X-API-Key`:

```bash
curl -H "X-API-Key: hub_test_XXXXXXXX…" https://sandbox.<domínio>/api/v1/developer/me
```

`Authorization: Bearer hub_test_…` também é aceito.

A chave entra **como a conta dona dela**: o sistema vê só os municípios dessa
conta, como o gestor vê no painel. Ela aparece uma única vez, na criação.
Guarde-a num cofre de segredos e nunca a coloque em código de navegador ou
aplicativo.

### Primeiro teste: `GET /developer/me`

Devolve a conta, os municípios do território e os limites da chave:

```json
{
  "ambiente": "test",
  "sandbox": true,
  "autenticacao": "api_key",
  "email": "integracao@parceiro.com.br",
  "municipios": ["2304400", "2611606", "3550308"],
  "chave": { "prefixo": "hub_test_a1B2c3", "escopo": "leitura",
             "limite_por_minuto": 30, "limite_por_dia": 2000 }
}
```

### Rotas mais usadas

A documentação interativa completa (OpenAPI) fica em `/api/v1/docs`. O
contrato em JSON fica em `/api/v1/openapi.json`, e dá para gerar um cliente
tipado a partir dele.

| O quê | Rota |
|---|---|
| Propostas do território (paginado, com filtros) | `GET /proposals?municipio=&ano=&situacao=&limite=&offset=` |
| Uma proposta | `GET /proposals/{id}` |
| Resumo financeiro | `GET /proposals/summary` |
| O que vence nos próximos dias | `GET /proposals/deadlines?dias=30` |
| Andamento / empenhos / emendas | `GET /proposals/{id}/timeline`, `/commitments`, `/amendments` |
| Repasses recebidos | `GET /transfers`, `GET /transfers/overview` |
| Alertas | `GET /alerts` |
| Favoritos (escopo escrita) | `GET/POST/DELETE /favorites` |
| Monitorar proposta (escopo escrita) | `POST /monitors` |

As rotas de recebidos e de outros eixos seguem os módulos liberados no plano
da conta. Módulo fora do plano responde `403 MODULO_NAO_INCLUIDO_PLANO`.

### Escopo da chave

- **`leitura`**: só `GET`. Tentativa de escrita responde `403 API_CHAVE_SOMENTE_LEITURA`.
- **`escrita`**: também favoritar, criar pastas, monitorar e marcar alertas como lidos.

### Rotas que a chave NÃO alcança

Administração, login e senha, gestão da conta (uma chave não cria outra),
copiloto de IA e qualquer consulta **ao vivo** nas fontes do governo. Isso
inclui `/proposals/live-search`, as rotas `…/sync`, o download de documentos
e os parâmetros `atualizar=true` e `conferir=true`. Os dados vêm do cache, que
é atualizado todo dia. Esses pedidos respondem
`403 API_ROTA_NAO_DISPONIVEL` ou `403 API_COLETA_AO_VIVO_NAO_DISPONIVEL`.

### Limites

Toda resposta traz:

```
X-RateLimit-Limit: 60            # por minuto, desta chave
X-RateLimit-Remaining: 57
X-RateLimit-Reset: 23            # segundos até a janela virar
X-RateLimit-Limit-Day: 10000
X-RateLimit-Remaining-Day: 9412
```

Ao passar do limite, a resposta é `429` com `Retry-After` (em segundos):

| Código (`detail`) | O que aconteceu | O que fazer |
|---|---|---|
| `API_LIMITE_MINUTO` | passou do limite por minuto | esperar `Retry-After` |
| `API_LIMITE_DIARIO` | acabou a cota do dia (UTC) | esperar a virada do dia ou pedir aumento |
| `API_SIMULTANEAS` | pedidos demais ao mesmo tempo | fazer em série (no máximo 2–3 em paralelo) |
| `API_LIMITE_GLOBAL` | a API está no teto de integrações | tentar de novo em instantes |

Recomendação: faça os pedidos em série, respeite o `Retry-After` e guarde o
resultado no seu sistema. Os dados mudam uma vez por dia; consultar a mesma
coisa a cada minuto só gasta cota.

### Erros de autenticação

| Status | `detail` | Causa |
|---|---|---|
| 401 | `API_CHAVE_INVALIDA` | chave errada, revogada, expirada ou conta desativada |
| 401 | `API_CHAVE_AMBIENTE_ERRADO` | chave de teste em produção ou vice-versa |

### Sandbox

- Os dados são **fictícios**: títulos começam com `[SANDBOX]`, o nº da proposta
  com `SBX`, e o registro bruto traz `"sandbox": true`. O território padrão é
  São Paulo/SP, Fortaleza/CE e Recife/PE.
- Nada sai do sandbox: não há e-mail, WhatsApp, push nem consulta às fontes.
- **Todo dia às 03:00 (Brasília)** os dados voltam ao estado original e o que a
  conta criou (favoritos, pastas, monitoramentos, alertas) é apagado.
- Para recomeçar na hora: `POST /developer/sandbox/reset` (chave com escopo
  `escrita`).
- Os limites do sandbox são menores que os da produção (padrão: 30 por minuto,
  2.000 por dia).

---

## Parte 2 — Para a operação

### Subir o sandbox no VPS atual (Dokploy)

O sandbox roda no mesmo servidor da produção, mas como outro projeto, com banco
próprio e teto de memória e CPU por serviço (cerca de 1,3 GB e 1,75 CPU no
total, no pior caso).

1. No Dokploy, crie um **projeto novo** (ex.: `hubcapture-sandbox`) → **Compose**,
   no mesmo repositório e branch da produção.
2. **Compose path:** `./docker-compose.sandbox.yml`.
3. **Environment** do projeto (é um `.env` separado do da produção):
   ```
   POSTGRES_PASSWORD=<senha nova>
   APP_DB_PASSWORD=<senha nova>
   JWT_SECRET=<openssl rand -hex 32>
   JWT_REFRESH_SECRET=<openssl rand -hex 32>
   CONFIG_SECRET_KEY=<openssl rand -hex 32>
   ADMIN_EMAIL=admin@seudominio.com.br
   ADMIN_PASSWORD=<senha>
   APP_BASE_URL=https://sandbox.seudominio.com.br
   ```
   **Não reaproveite os segredos da produção.** Um token emitido num ambiente
   não pode valer no outro. `SANDBOX=true` e o banco já vêm fixos no compose: um
   `.env` copiado da produção não desliga o modo sandbox nem aponta para o banco
   de produção.
4. **Domains:** `sandbox.seudominio.com.br` → serviço `sbx-web`, porta `3000`.
5. Deploy. Confira em `https://sandbox.seudominio.com.br/api/v1/ui`: a resposta
   deve trazer `"sandbox": true`. O site mostra a faixa amarela "Ambiente de
   testes" em todas as telas.

Os serviços do sandbox se chamam `sbx-*` de propósito. A produção e o sandbox
dividem a rede do proxy (`dokploy-network`); se os dois tivessem um serviço
`api` nela, a web de um poderia acabar falando com a API do outro.

### Liberar a API para um cliente (produção)

1. **Admin → Planos → Configurar**: ligue a feature **"API de integração"** e,
   se quiser, defina as requisições por minuto, por dia e o número de chaves.
   Campos vazios usam o padrão do servidor (60/min, 10.000/dia, 5 chaves).
2. O cliente cria as próprias chaves em **Minha conta → Integração via API**.
3. Também dá para emitir a chave pela administração: **Admin → Chaves de API**.
   Escolha a conta e, se quiser, sobreponha os limites daquela chave. A
   administração emite mesmo sem a feature no plano.

Contas de administração (superusuário) nunca recebem chave. A integração deve
usar uma conta própria, com o território que ela pode ver.

### Revogar

Na lista de chaves (conta ou admin), **Revogar**. O efeito é imediato neste
processo da API. Conta desativada também perde todas as chaves.

### Proteção da aplicação

O painel dos gestores e os parceiros dividem o mesmo processo da API. Por isso,
o tráfego que chega por chave tem tetos próprios (variáveis no `.env`):

| Variável | Padrão | O que limita |
|---|---|---|
| `API_LIMITE_POR_MINUTO` | 60 | por chave, quando o plano não define |
| `API_LIMITE_POR_DIA` | 10000 | por chave, quando o plano não define |
| `API_LIMITE_GLOBAL_POR_MINUTO` | 600 | todos os parceiros somados |
| `API_MAX_SIMULTANEAS` | 8 | pedidos de parceiros em andamento ao mesmo tempo |
| `API_MAX_SIMULTANEAS_POR_CHAVE` | 3 | idem, por chave |
| `API_CHAVES_MAX_POR_CONTA` | 5 | chaves ativas, quando o plano não define |

O tráfego do painel (login normal) não passa por esses limites.

O consumo de cada chave por dia fica na tabela `api_uso` e aparece nas listas
de chaves (hoje, últimos 30 dias, pedidos barrados). Serve de base para
cobrança.
