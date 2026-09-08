# Ficha do pedido — dados para o formulário e-Software

Campos do formulário do INPI já levantados a partir do repositório. O que está
como `[preencher]` depende de decisão sua, não do código.

## Dados do programa

Valores para o formulário e-Software, com os códigos das tabelas do próprio INPI.

| Campo do formulário | Valor |
|---|---|
| Título | **Hub Capture** |
| Data de criação | `[preencher]` — ver critério abaixo |
| Data de publicação | `[preencher]` — só se já está acessível ao público |
| Linguagem (repetível) | **Python**, **TypeScript**, **SQL** |
| Campo de Aplicação | **AD04 — Adm Publ** (Administr. Federal, Estadual, **Municipal**…) |
| Tipo de Programa | **IA01 — Inteligência Artificial** (alternativa conservadora: AP01 — Aplicativos) |
| Algorítimo hash | **SHA-512 — Secure Hash Algorithm** |
| Resumo digital hash | copiar de `dist/inpi/*.hash.txt` (128 caracteres hex) |
| Derivação Autorizada | **deixar desmarcado** — ver abaixo |

**Campo de Aplicação = o setor onde o programa é aplicado**, não o assunto que ele
trata. O gestor público municipal é o usuário, então AD04. `FN01 — Finan Públ`
(receita pública, orçamento, despesa) é o segundo mais próximo e serve se a leitura
preferida for a financeira; se o formulário aceitar mais de um, valem os dois.

**Tipo de Programa**: `IA01` é sustentado pelo código que acompanha o pacote
(agente com chamada de ferramentas, curadoria por modelo de linguagem, embeddings
e busca semântica) e é coerente com a originalidade declarada na identificação.
`AP01 — Aplicativos` é a opção genérica, também correta e mais conservadora. Se o
campo aceitar mais de um, `AP03 — Controle` cobre a vigilância das propostas.

**Derivação Autorizada — deixar desmarcado.** O campo trata do art. 5º da Lei
9.609/98: programa derivado de OUTRO programa, com autorização do titular daquele.
Não é o caso. Usar bibliotecas de terceiros (FastAPI, Next.js, SQLAlchemy) **não**
é derivação — marcar "Sim" obrigaria a guardar um documento de autorização que não
existe.

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

Texto para o campo de descrição do e-Software. É ele que caracteriza a criação
para o examinador — e, num litígio, é por ele que se argumenta o que o programa
faz de próprio. Por isso abre pela **IA lendo o perfil**, que é o diferencial em
relação às demais plataformas de captação, e não pela lista de fontes de dados,
que qualquer concorrente também tem.

> Plataforma web que concentra, organiza e monitora propostas, editais e
> repasses de recursos das plataformas de transferência voluntária do governo
> federal brasileiro, voltada ao gestor público municipal. O programa emprega
> inteligência artificial para interpretar as demandas e necessidades do
> município e do gestor e, a partir dessa leitura do perfil — território, áreas
> de atuação, papel do usuário e histórico de acompanhamento —, selecionar entre
> as oportunidades disponíveis as pertinentes àquele município e sugerir o
> acompanhamento das propostas correspondentes, ajustando seleção e sugestões à
> medida que apura o entendimento do perfil. Reúne ainda cadastro conversacional
> conduzido por assistente, curadoria automática em duas camadas
> (classificação determinística e refinamento por modelo de linguagem),
> copiloto com chamada de ferramentas sobre as próprias funções do sistema,
> vigilância de propostas por critérios escolhidos pelo usuário com detecção de
> alteração por comparação de estados sucessivos, e ingestão combinada por
> interface de programação e extração automatizada de páginas com fusão por
> precedência declarada de campo. Arquitetura multi-inquilino com isolamento por
> usuário no banco de dados.

### Diferenciação frente aos concorrentes

O `00-IDENTIFICACAO.txt` do pacote traz a seção **Características originais**,
que detalha os seis pontos e diz explicitamente o que as outras plataformas
fazem de diferente. O mais relevante — e o que sustenta os demais:

> As soluções concorrentes organizam a interface **por plataforma de origem**
> (uma aba para o TransfereGov, outra para o FNS, outra para o FNDE), cabendo ao
> gestor percorrer fonte por fonte. No Hub Capture a navegação parte do
> **perfil**; as fontes são detalhe interno de ingestão e não aparecem como
> divisão da interface.

Vale como caracterização de originalidade porque é uma **decisão de arquitetura
verificável no código** que acompanha o pacote (a navegação por lentes sobre o
território, a derivação das fontes a partir das áreas declaradas), não uma
alegação de marketing. Ao registrar uma versão nova, revise essa seção: é ela
que envelhece primeiro.

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
