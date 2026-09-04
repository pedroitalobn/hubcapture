# Registro do Hub Capture no INPI — programa de computador

Guia operacional do pedido de **Registro de Programa de Computador (RPC)** do Hub
Capture, com o que é feito aqui no repositório (o pacote e o hash) e o que é feito
no site do INPI.

> Isto é orientação técnica de engenharia, não parecer jurídico. Titularidade,
> cessão de direitos entre sócios/contratados e estratégia de proteção valem uma
> conversa com um advogado de PI — sobretudo os pontos marcados **⚠** ao final.

---

## O que o registro é (e o que não é)

O direito autoral sobre o software **já existe desde a criação**, independentemente
de registro (Lei 9.609/98, art. 2º). O registro no INPI é **facultativo** e serve
como **prova de anterioridade e de integridade**: prova que, naquela data, aquele
código exato existia e era seu.

O ponto central do procedimento atual: **o INPI não recebe o código-fonte.** Ele
recebe apenas o **resumo digital hash** do arquivo com a documentação técnica. O
arquivo fica com você. O hash vai impresso no certificado — e é ele que, num
litígio, o perito usa para conferir que o arquivo que você apresenta é o mesmo que
foi registrado.

Consequência prática, e é a mais importante deste documento:

> **Se o arquivo `.zip` se perder ou for alterado (mesmo recompactado), o registro
> perde a serventia probatória.** Guarde-o intacto, em mais de um lugar.

O registro vale **50 anos**, contados de 1º de janeiro do ano seguinte ao da
publicação ou, na falta desta, da criação (Lei 9.609/98, art. 2º, §2º).

---

## Passo 0 — Decidir o titular (antes de tudo)

O **autor** é sempre pessoa física; o **titular** é quem detém os direitos
patrimoniais e pode ser PF ou PJ.

- Se o Hub Capture é produto de uma empresa, registre em nome da **PJ**, com os
  autores nomeados. Programa desenvolvido por empregado ou prestador **no âmbito
  do contrato** pertence ao contratante (Lei 9.609/98, art. 4º).
- Se ainda não há PJ, registre em nome da **PF** — depois é possível transferir a
  titularidade ao INPI (petição própria, com custo).

Registrar em nome errado e corrigir depois custa mais caro do que decidir agora.

---

## Passo 1 — Gerar o pacote e o hash (aqui no repositório)

```bash
python3 scripts/inpi/gerar_pacote_inpi.py
```

O script exige árvore limpa (sem alterações não commitadas), porque o pacote
carimba o commit de origem. Ele produz, em `dist/inpi/`:

| Arquivo | O que é |
|---|---|
| `hubcapture-documentacao-tecnica-AAAAMMDD-<commit>.zip` | **A documentação técnica.** É este arquivo que você guarda. |
| `...hash.txt` | O recibo: SHA-512, tamanho, commit e data de geração. |

Dentro do `.zip`:

- `00-IDENTIFICACAO.txt` — título, commit, contagem de arquivos/linhas, linguagens;
- `01-INVENTARIO.txt` — **SHA-256 de cada arquivo**, individualmente;
- `codigo-fonte/…` — o código versionado (Python, TypeScript/TSX, SQL das
  migrations, CSS, Dockerfiles, compose, docs de arquitetura).

Ficam **de fora**: dependências (`node_modules`, `.venv`), lockfiles, binários e
qualquer `.env` — não são criação intelectual e `.env` é risco de vazamento.

Três propriedades que valem a pena entender, porque são o que dá força à prova:

1. **É determinístico.** Duas gerações a partir do mesmo commit produzem o mesmo
   arquivo, byte a byte, e portanto o mesmo hash — em qualquer máquina. Nada
   dentro do pacote depende do relógio, e o `.zip` é armazenado **sem compressão**
   justamente porque a saída do compressor varia entre versões de biblioteca.
2. **Aponta para um commit.** O `00-IDENTIFICACAO.txt` traz o SHA do commit — dá
   para reconstruir o pacote e reconferir o hash a qualquer momento.
3. **Tem inventário por arquivo.** Se um dia houver dúvida sobre um trecho
   específico, o SHA-256 individual resolve sem depender do zip inteiro.

Conferir o hash de um pacote já gerado:

```bash
python3 scripts/inpi/gerar_pacote_inpi.py --verificar dist/inpi/<arquivo>.zip
# ou, sem o script:
sha512sum dist/inpi/<arquivo>.zip
```

### Guarda do arquivo (faça agora, não depois)

- No mínimo **duas cópias** em mídias distintas (ex.: um HD/pendrive offline + um
  armazenamento em nuvem privado).
- **Não abra, não renomeie internamente, não recompacte.** Qualquer disso muda o
  hash. Copiar o arquivo inteiro é seguro; mexer nele não é.
- Guarde o `...hash.txt` junto, e anote o hash também fora do computador.
- Opcional, reforça a data: registrar o hash em cartório de títulos e documentos,
  ou publicá-lo num canal datado (o próprio commit no GitHub já ajuda).

---

## Passo 2 — Cadastro no e-INPI

Crie o cadastro em <https://www.gov.br/inpi> → *Serviços* → *Programas de
Computador*. O cadastro é do **titular** (CPF ou CNPJ). Se for PJ, o representante
legal precisa estar habilitado.

Tenha à mão um **certificado digital ICP-Brasil** (e-CPF/e-CNPJ) ou a conta
**gov.br nível prata ou ouro** — a Declaração de Veracidade precisa ser assinada
digitalmente.

## Passo 3 — Emitir e pagar a GRU

- Serviço: **código 730 — Pedido de registro de programa de computador (RPC)**.
- Valor: **R$ 210,00** na tabela vigente em 2026. Atenção: a Portaria INPI/PR nº
  10/2025 **não estendeu aos serviços de software** o desconto de 50% que vale
  para marcas e patentes — para o 730 não há valor reduzido para pessoa física,
  ME/EPP ou instituição de ensino. **Confira a tabela no dia**, ela muda.
- Ao emitir a GRU, **baixe também a Declaração de Veracidade (DV)** disponibilizada
  pelo sistema. Ela precisa ser **assinada digitalmente** e anexada no passo
  seguinte.
- Só prossiga após o **pagamento compensar** (costuma levar 1–2 dias úteis).

## Passo 4 — Preencher o formulário e-Software

No módulo **e-Software**, com a GRU paga:

| Campo | O que informar no caso do Hub Capture |
|---|---|
| **Título** | `Hub Capture` |
| **Data de criação** | A data em que o programa passou a cumprir plenamente a função a que se destina — **não** a data do primeiro commit. Ver a ficha em `ficha-do-pedido.md`. |
| **Data de publicação** | Só se já estiver acessível ao público (em produção). Se não estiver, deixe em branco. |
| **Linguagens** | Python, TypeScript, SQL (as principais; a ficha traz a contagem) |
| **Campo de aplicação** | Escolher na lista do próprio formulário (administração pública / gestão) |
| **Tipo de programa** | Escolher na lista (sistema aplicativo / aplicação web) |
| **Autores** | Pessoas físicas, com CPF. Podem ser dispensados de nomeação a pedido. |
| **Titular** | PF ou PJ, conforme o Passo 0 |
| **Algoritmo** | `SHA-512` |
| **Resumo digital hash** | O valor do `...hash.txt` (128 caracteres hexadecimais) |

Anexe a **Declaração de Veracidade assinada** e finalize.

As listas de *campo de aplicação* e *tipo de programa* são do INPI e aparecem no
próprio formulário — escolha lá, em vez de decorar código, que a tabela muda.

## Passo 5 — Acompanhar

A publicação na **RPI** costuma sair em até **10 dias** contados do pedido. Depois
dela, o **certificado** fica disponível para download no e-INPI, já com o hash
impresso.

Se vier **exigência**, o prazo de resposta é curto — acompanhe a RPI ou o e-mail
cadastrado.

---

## Depois do registro

- **Versões novas não são cobertas automaticamente.** O registro protege *aquele*
  código. Alteração relevante (novo módulo, mudança de arquitetura) pede **novo
  pedido**, com novo pacote e novo hash. Correção de bug não pede.
- Uma cadência razoável: um registro por marco de produto, e sempre antes de
  apresentar o sistema a cliente grande, licitação ou investidor.
- **A marca “Hub Capture” é outro registro**, na via de marcas (classes NCL 9 e
  42). O RPC protege o código; a marca protege o nome. São pedidos e taxas
  separados.

---

## ⚠ Pontos para conferir com um advogado de PI

1. **Autoria e ferramentas de IA.** Parte do histórico deste repositório tem
   commits co-assinados por assistente de IA (`Co-Authored-By: Claude`). No direito
   brasileiro o autor é pessoa física; a corrente majoritária atribui a autoria ao
   humano que dirigiu, selecionou e integrou o resultado. O formulário pede autores
   pessoas físicas e a DV é declaração de veracidade sob responsabilidade —
   vale alinhar com o advogado **como declarar** antes de assinar.
2. **Cessão de direitos.** Se houve colaborador, sócio ou prestador sem contrato
   escrito de cessão, resolva isso **antes** do registro.
3. **Dependências de terceiros e licenças.** O pacote contém só código próprio,
   mas o produto se apoia em bibliotecas de terceiros com licenças próprias. Isso
   não impede o registro; impacta distribuição e licenciamento.
