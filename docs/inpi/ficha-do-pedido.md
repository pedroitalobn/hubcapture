# Ficha do pedido — dados para o formulário e-Software

Campos do formulário do INPI já levantados a partir do repositório. O que está
como `[preencher]` depende de decisão sua, não do código.

## Dados do programa

| Campo do formulário | Valor |
|---|---|
| Título | **Hub Capture** |
| Data de criação | `[preencher]` — ver critério abaixo |
| Data de publicação | `[preencher]` — só se já está acessível ao público |
| Linguagens de programação | **Python**, **TypeScript**, **SQL** (+ CSS, HTML, Shell) |
| Campo de aplicação | escolher na lista do e-Software (administração pública / gestão) |
| Tipo de programa | escolher na lista do e-Software (sistema aplicativo / aplicação web) |
| Algoritmo do resumo | **SHA-512** |
| Resumo digital hash | copiar de `dist/inpi/*.hash.txt` (128 caracteres hex) |

### Data de criação — como escolher

Para o INPI, é **a data em que o programa passou a atender plenamente as funções
para as quais foi concebido** — não a data do primeiro commit nem a de hoje.

Referências do repositório para embasar a escolha:

- primeiro commit: **2026-08-09**;
- histórico com **158 commits** até o commit de referência do pacote;
- o produto já cobre ponta a ponta: autenticação, onboarding, ingestão das fontes
  (TransfereGov e FNS), captação, recebidos, alertas, copiloto e painel admin.

Na dúvida entre duas datas, a mais defensável é aquela em que a versão funcional
foi para o ar / foi demonstrada — algo que você consiga comprovar por outro meio
(deploy, e-mail, apresentação a cliente).

## Descrição sugerida do programa

> Plataforma web que concentra, organiza e monitora propostas, editais e repasses
> de recursos das plataformas de transferência voluntária do governo federal
> brasileiro (TransfereGov e Fundo Nacional de Saúde), com ingestão automatizada
> por conectores de API e extração de páginas, normalização e deduplicação em
> esquema canônico, curadoria assistida por modelos de linguagem, detecção de
> alterações com alertas por painel, e-mail e WhatsApp, e um copiloto
> conversacional com acesso às ferramentas do próprio sistema. Arquitetura
> multi-inquilino com isolamento por usuário no banco de dados.

## Composição da documentação técnica

Números do pacote gerado (conferir no `00-IDENTIFICACAO.txt` de cada geração):

- **451 arquivos**, ~**112 mil linhas**, ~4,3 MB;
- Python (316 arquivos) — API FastAPI, conectores, ingestão, jobs, camada de IA;
- TypeScript/TSX (95 arquivos) — aplicação web Next.js;
- SQL — migrations e políticas de isolamento por inquilino;
- + CSS (design system), HTML, Shell, Dockerfiles e documentação de arquitetura.

## Autores e titular

| Papel | Quem | Documento |
|---|---|---|
| Autor | Pedro Italo Benevides | CPF `[preencher]` |
| Autor(es) adicional(is) | `[preencher, se houver]` | |
| Titular | `[preencher: a mesma PF, ou a PJ]` | CPF/CNPJ `[preencher]` |

Contribuidores identificados no histórico do repositório: `Pedro Benevides` /
`Pedro Italo` (mesmo e-mail) e commits co-assinados por assistente de IA — ver a
ressalva **⚠ 1** no `README.md` desta pasta antes de preencher.

## Anexos e taxa

- **Declaração de Veracidade (DV)** assinada digitalmente (ICP-Brasil ou gov.br
  prata/ouro) — baixada junto com a GRU.
- **GRU código 730**, R$ 210,00 (tabela 2026 — conferir no dia), paga e compensada
  antes de preencher o formulário.
