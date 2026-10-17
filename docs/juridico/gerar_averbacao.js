/**
 * Gera o documento de averbação / declaração de autoria do Hub Capture (.docx).
 * Uso: node gerar_averbacao.js <caminho-de-saida.docx>
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, Footer, PageNumber, LevelFormat, convertMillimetersToTwip,
} = (() => {
  // usa o docx instalado localmente (npm i docx) ou o do diretório do script
  try { return require("docx"); } catch { return require(path.join(__dirname, "node_modules", "docx")); }
})();

const FONT = "Times New Roman";
const SIZE = 24;      // 12pt
const SIZE_SM = 20;   // 10pt
const CONTENT_W = 8504; // A4 (11906) - margens 1701*2

/* ---------------------------------------------------------------- helpers */

const P = (text, o = {}) =>
  new Paragraph({
    alignment: o.align ?? AlignmentType.JUSTIFIED,
    spacing: { after: o.after ?? 160, line: o.line ?? 300 },
    indent: o.indent,
    keepNext: o.keepNext,
    border: o.border,
    children: [
      new TextRun({ text, font: FONT, size: o.size ?? SIZE, bold: o.bold, italics: o.italics }),
    ],
  });

/** Parágrafo com trechos mistos: [{t, bold, italics}] */
const PR = (runs, o = {}) =>
  new Paragraph({
    alignment: o.align ?? AlignmentType.JUSTIFIED,
    spacing: { after: o.after ?? 160, line: o.line ?? 300 },
    indent: o.indent,
    children: runs.map(
      (r) =>
        new TextRun({
          text: r.t,
          font: FONT,
          size: o.size ?? SIZE,
          bold: r.bold,
          italics: r.italics,
          allCaps: r.caps,
        }),
    ),
  });

const H1 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    alignment: AlignmentType.LEFT,
    spacing: { before: 360, after: 200 },
    keepNext: true,
    children: [new TextRun({ text, font: FONT, size: SIZE, bold: true, allCaps: true })],
  });

const H2 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_2,
    alignment: AlignmentType.LEFT,
    spacing: { before: 240, after: 140 },
    keepNext: true,
    children: [new TextRun({ text, font: FONT, size: SIZE, bold: true })],
  });

const BULLET = (text, level = 0) =>
  new Paragraph({
    numbering: { reference: "lista", level },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 100, line: 300 },
    children: [new TextRun({ text, font: FONT, size: SIZE })],
  });

const cell = (text, { widths, i, bold, head, align } = {}) =>
  new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: "E7E9EC", color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [
      new Paragraph({
        alignment: align ?? AlignmentType.LEFT,
        spacing: { after: 0, line: 260 },
        children: [new TextRun({ text, font: FONT, size: SIZE_SM, bold: bold || head })],
      }),
    ],
  });

/** rows: array de arrays de string. Primeira linha = cabeçalho (opcional). */
const T = (widths, rows, { header = true, boldFirstCol = false } = {}) =>
  new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "999999" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "BBBBBB" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "BBBBBB" },
    },
    rows: rows.map(
      (r, ri) =>
        new TableRow({
          tableHeader: header && ri === 0,
          children: r.map((c, i) =>
            cell(c, { widths, i, head: header && ri === 0, bold: boldFirstCol && i === 0 && !(header && ri === 0) }),
          ),
        }),
    ),
  });

const SPACER = (after = 200) => new Paragraph({ spacing: { after }, children: [] });

const linhaAssinatura = (rotulo) => [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 520, after: 0 },
    border: { top: { style: BorderStyle.SINGLE, size: 6, color: "000000", space: 4 } },
    children: [],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240, line: 260 },
    children: [new TextRun({ text: rotulo, font: FONT, size: SIZE_SM })],
  }),
];

/* ----------------------------------------------------------------- dados */

const HASH =
  "24f54633ecfa8c28eb1b95a4d1e7f2596afc302d065c0e6538f57ddc10ddd27b" +
  "ec5b088c54384d25f7c6b9c13e8af2f46000832b5e5b927b8eba070394e089da";

const PH = (t) => ({ t, bold: true }); // placeholder a preencher

/* ------------------------------------------------------------- documento */

const filhos = [];

// ---- Cabeçalho / título
filhos.push(
  P("DECLARAÇÃO DE AUTORIA E TITULARIDADE", { align: AlignmentType.CENTER, bold: true, after: 60 }),
  P("E MEMORIAL DESCRITIVO DE PROGRAMA DE COMPUTADOR", { align: AlignmentType.CENTER, bold: true, after: 60 }),
  P("APLICATIVO “HUB CAPTURE”", { align: AlignmentType.CENTER, bold: true, after: 240 }),
  P(
    "Instrumento particular lavrado para fins de averbação e registro, nos termos da Lei nº 9.609, de 19 de fevereiro de 1998 (Lei do Software), da Lei nº 9.610, de 19 de fevereiro de 1998 (Lei de Direitos Autorais), do Decreto nº 2.556, de 20 de abril de 1998, e da Lei nº 6.015, de 31 de dezembro de 1973 (Lei de Registros Públicos).",
    { align: AlignmentType.CENTER, size: SIZE_SM, after: 360, italics: true },
  ),
);

// ---- Qualificação
filhos.push(H1("I – Da qualificação do autor e titular"));
filhos.push(
  PR(
    [
      PH("[NOME COMPLETO DO AUTOR]"),
      { t: ", " },
      PH("[nacionalidade]"),
      { t: ", " },
      PH("[estado civil]"),
      { t: ", " },
      PH("[profissão]"),
      { t: ", nascido(a) em " },
      PH("[data de nascimento]"),
      { t: ", filho(a) de " },
      PH("[nome do pai]"),
      { t: " e de " },
      PH("[nome da mãe]"),
      { t: ", portador(a) da Cédula de Identidade RG nº " },
      PH("[número]"),
      { t: ", expedida por " },
      PH("[órgão expedidor/UF]"),
      { t: ", inscrito(a) no Cadastro de Pessoas Físicas do Ministério da Fazenda sob o nº " },
      PH("[000.000.000-00]"),
      { t: ", residente e domiciliado(a) na " },
      PH("[logradouro, número, complemento, bairro]"),
      { t: ", CEP " },
      PH("[00000-000]"),
      { t: ", no Município de " },
      PH("[cidade]"),
      { t: ", Estado " },
      PH("[UF]"),
      { t: ", com endereço eletrônico " },
      PH("[e-mail]"),
      { t: " e telefone " },
      PH("[(00) 00000-0000]"),
      { t: ", doravante denominado(a) simplesmente " },
      { t: "AUTOR E TITULAR", bold: true },
      {
        t: ", na condição de pessoa física criadora, de forma independente e por conta e risco próprios, do programa de computador adiante descrito, vem, por este instrumento particular, DECLARAR, sob as penas da lei e para os fins de direito, o quanto segue.",
      },
    ].filter(Boolean),
  ),
);

// ---- Objeto
filhos.push(H1("II – Do objeto"));
filhos.push(
  P(
    "2.1. O presente documento tem por objeto declarar a autoria e a titularidade, descrever tecnicamente e instruir o pedido de averbação e/ou registro do programa de computador denominado “HUB CAPTURE”, aplicativo de concentração, curadoria e monitoramento de propostas, editais, repasses e obras custeados por recursos públicos federais brasileiros, destinado a gestores públicos municipais, parlamentares e suas equipes técnicas.",
  ),
  P(
    "2.2. O programa foi integralmente concebido, projetado, especificado e desenvolvido pelo AUTOR, que detém, em caráter originário, exclusivo e vitalício, a integralidade dos direitos morais e patrimoniais sobre a obra, na forma do art. 2º da Lei nº 9.609/1998 c/c o art. 22 da Lei nº 9.610/1998.",
  ),
);

// ---- Identificação
filhos.push(H1("III – Da identificação do programa de computador"));
filhos.push(
  T(
    [2900, 5604],
    [
      ["Campo", "Conteúdo"],
      ["Título do programa", "Hub Capture"],
      ["Denominação técnica do repositório", "hubcapture (monorepo)"],
      ["Versão objeto desta declaração", "1.0"],
      ["Tipo de programa", "Aplicação web (SaaS) com interface de programação de aplicações (API) pública versionada e cliente web; arquitetura preparada para cliente móvel"],
      ["Campo de aplicação", "Administração pública; gestão de convênios, transferências voluntárias e obrigatórias, emendas parlamentares e obras públicas; ciência de dados aplicada a dados abertos governamentais"],
      ["Linguagens de programação", "Python 3.12 (núcleo, API e ingestão); TypeScript / TSX (interface web); SQL (modelo relacional e políticas de segurança)"],
      ["Sistema operacional / plataforma", "Independente de plataforma — execução em contêineres Linux (Docker); acesso pelo navegador"],
      ["Sistema gerenciador de banco de dados", "PostgreSQL 16 com extensão vetorial pgvector"],
      ["Data de criação (primeiro registro de versionamento)", "08 de julho de 2026"],
      ["Data da versão declarada", "24 de julho de 2026"],
      ["Resumo digital hash (SHA-512) do código-fonte", HASH],
      ["Identificador da revisão de código correspondente", "4e9709d29d79ccf4680773d214b5f28708eef4a2"],
    ],
  ),
  SPACER(160),
  P(
    "3.1. O resumo digital hash acima foi obtido pelo algoritmo SHA-512 aplicado sobre o arquivo consolidado do código-fonte na revisão indicada. No ato do depósito perante o Instituto Nacional da Propriedade Industrial – INPI, o resumo deverá ser regerado sobre o arquivo efetivamente depositado, na forma da Resolução do INPI aplicável, e o valor apurado consignado no formulário eletrônico.",
    { size: SIZE_SM },
  ),
);

// ---- Finalidade
filhos.push(H1("IV – Do problema técnico solucionado e da finalidade"));
filhos.push(
  P(
    "4.1. As informações sobre recursos federais disponíveis e efetivamente transferidos a municípios brasileiros encontram-se dispersas em dezenas de plataformas governamentais autônomas — TransfereGov (transferências fundo a fundo, especiais e discricionárias), Fundo Nacional de Saúde, Fundo Nacional de Desenvolvimento da Educação, Fundo de Participação dos Municípios, portais de emendas parlamentares, sistemas de conformidade fiscal e sistemas de acompanhamento de obras —, cada qual com padrão próprio de identificação, periodicidade de atualização, nomenclatura e meio de acesso, sendo que parte relevante sequer disponibiliza interface programática de consulta.",
  ),
  P(
    "4.2. O programa soluciona esse problema técnico ao implementar um núcleo de ingestão multifonte que, para um mesmo território — identificado sempre pelo código do município no Instituto Brasileiro de Geografia e Estatística, com sete dígitos, adotado como chave canônica —, coleta, normaliza, deduplica, concilia e historia registros heterogêneos em um esquema de dados único, entregando ao gestor público uma visão consolidada e temporalmente comparável do ciclo completo do recurso público: captar, receber, executar e prestar contas.",
  ),
  P(
    "4.3. Constitui característica distintiva da criação a estratégia de coleta combinada: para cada fonte que disponha simultaneamente de interface programática e de página de consulta, ambas as rotas são executadas e seus resultados são fundidos segundo regra de precedência por campo — prevalecendo a interface programática nos identificadores, valores e datas, e a extração da página nos campos descritivos de situação, pendências e movimentação —, registrando-se a origem de cada valor em estrutura de proveniência, o que assegura auditabilidade do dado e degradação graciosa em caso de indisponibilidade de qualquer das rotas.",
  ),
  P(
    "4.4. Constitui igualmente característica distintiva a organização da navegação centrada no perfil do usuário — território, áreas de interesse e papel institucional —, e não na fonte de dados de origem, de modo que a inclusão de novas fontes é absorvida pelo núcleo de ingestão sem alteração da interface apresentada ao usuário.",
  ),
);

// ---- Descrição funcional
filhos.push(H1("V – Da descrição funcional"));
filhos.push(P("5.1. O programa é composto pelos seguintes módulos funcionais:"));
filhos.push(
  T(
    [2400, 6104],
    [
      ["Módulo", "Funcionalidade"],
      ["Identidade e acesso", "Cadastro, autenticação por token JSON Web Token com renovação, recuperação e redefinição de senha, verificação de endereço eletrônico, gestão de conta e fluxo de convites."],
      ["Integração de perfil (onboarding)", "Captura dos municípios de interesse, das áreas temáticas e do papel institucional do usuário, com disparo da primeira sincronização dirigida."],
      ["Captação", "Consulta, filtragem e detalhamento de propostas, convênios e editais, com leitura prioritária em cache e consulta avulsa sob demanda quando o dado estiver ausente ou desatualizado."],
      ["Recursos recebidos", "Consolidação de repasses efetivamente recebidos pelo município, com decomposição entre créditos e deduções e apuração de valores líquidos por período e por fonte."],
      ["Conformidade fiscal", "Apuração de indicadores de regularidade e de capacidade de pagamento do ente, com resumo por situação e por seção."],
      ["Obras", "Acompanhamento da execução física e financeira de obras públicas, com percentual de execução, situação e georreferenciamento."],
      ["Curadoria", "Favoritos, pastas classificatórias e organização pessoal do acervo de oportunidades."],
      ["Monitoramento e alertas", "Detecção de alteração por comparação de resumo criptográfico de conteúdo, geração de alertas tipificados por situação, prazo e pendência, e despacho por painel, correio eletrônico e mensageria."],
      ["Inteligência artificial", "Geração de resumo assistido no fluxo de ingestão, copiloto de orientação processual e conversação sobre o acervo próprio do usuário, com recuperação semântica apoiada em vetores de similaridade."],
      ["Exportação", "Emissão de relatório em formato de documento portátil a partir dos registros selecionados."],
      ["Administração da plataforma", "Gestão de usuários, papéis, planos e convites, e painel de configuração das credenciais e endereços dos provedores externos em tempo de execução, com cifragem em repouso e mascaramento na leitura."],
    ],
  ),
);

// ---- Arquitetura
filhos.push(H1("VI – Da arquitetura técnica"));
filhos.push(
  P(
    "6.1. O programa adota arquitetura orientada a interface de programação: uma única API pública versionada, implementada em Python com o arcabouço FastAPI, concentra a totalidade das regras de negócio, do acesso a dados e da comunicação com fontes externas; as interfaces de apresentação — cliente web e, em fase subsequente, cliente móvel — consomem exatamente o mesmo contrato, gerado automaticamente a partir da especificação OpenAPI, sendo-lhes vedado o acesso direto ao banco de dados ou às fontes governamentais.",
  ),
  P("6.2. O código encontra-se organizado nas seguintes camadas:"),
  BULLET("núcleo de configuração, segurança e injeção de dependências;"),
  BULLET("camada de persistência, com mapeamento objeto-relacional assíncrono e versionamento incremental do esquema por migrações;"),
  BULLET("camada de conectores, um módulo por fonte de dados, todos aderentes a um mesmo protocolo de coleta e verificação de disponibilidade, com política compartilhada de repetição e recuo exponencial;"),
  BULLET("camada de ingestão, responsável pela normalização ao esquema canônico, pela fusão multifonte, pela deduplicação, pelo cálculo do resumo de conteúdo e pela detecção de alterações;"),
  BULLET("camada de serviços, que implementa as regras de negócio, entre elas a leitura prioritária em cache com validade temporal;"),
  BULLET("camada de inteligência artificial, com roteamento de modelos, geração de vetores de representação e fluxos conversacionais;"),
  BULLET("camada de exposição, composta pelos roteadores da API e pelos esquemas de entrada e saída validados;"),
  BULLET("camada de apresentação web, construída em React sobre Next.js, restrita à apresentação."),
  P(
    "6.3. A execução em produção dá-se por contêineres orquestrados, compreendendo os serviços de banco de dados, interface de programação, aplicação web, cache e mecanismo de agendamento de rotinas.",
  ),
);

// ---- Fontes
filhos.push(H1("VII – Das fontes de dados integradas"));
filhos.push(
  P(
    "7.1. Os conectores implementados, todos aderentes ao mesmo protocolo e substituíveis sem alteração do núcleo, contemplam as seguintes fontes públicas de dados:",
  ),
  T(
    [2100, 2500, 3904],
    [
      ["Eixo do ciclo", "Fonte", "Natureza da coleta"],
      ["Captação", "TransfereGov – fundo a fundo", "Interface programática"],
      ["Captação", "TransfereGov – transferências especiais", "Interface programática com fusão e contingência por extração"],
      ["Captação", "TransfereGov – discricionárias", "Carga periódica de arquivo aberto"],
      ["Captação", "Fundo Nacional de Saúde", "Extração estruturada de página"],
      ["Captação", "Fundo Nacional de Desenvolvimento da Educação", "Interface programática com fusão por extração"],
      ["Captação", "SERPRO", "Interface programática — enriquecimento"],
      ["Recursos recebidos", "Fundo de Participação dos Municípios", "Interface programática"],
      ["Recursos recebidos", "Emendas parlamentares", "Interface programática"],
      ["Conformidade fiscal", "Siconfi / Tesouro Transparente", "Carga de arquivo aberto"],
      ["Obras", "SISMOB", "Interface programática"],
      ["Obras", "SIMEC", "Interface programática"],
      ["Obras", "CAIXA / obras federais", "Interface programática"],
    ],
  ),
  SPACER(140),
  P(
    "7.2. O acesso às fontes restringe-se a dados públicos e abertos, disponibilizados pelos próprios órgãos federais, observados os limites de uso por eles estabelecidos, sem qualquer forma de contorno de controle de acesso.",
  ),
);

// ---- Modelo de dados e segurança
filhos.push(H1("VIII – Do modelo de dados, da segurança e da proteção de dados pessoais"));
filhos.push(
  P(
    "8.1. O modelo relacional compreende, entre outras, as entidades de usuários, municípios de interesse, preferências, propostas, repasses, conformidades, obras, favoritos, pastas, monitoramentos, alertas, execuções de sincronização, planos, convites, configurações, base de conhecimento, vetores de representação e registro de auditoria.",
  ),
  P(
    "8.2. O isolamento entre assinantes é implementado no próprio banco de dados, por políticas de segurança em nível de linha, ativadas para toda entidade vinculada a usuário e para as entidades de cache territorial; a identidade do usuário é fixada na sessão de banco a cada requisição, a partir do token autenticado, e a aplicação conecta-se por credencial desprovida de privilégios de superusuário, de modo que a política não possa ser contornada pela camada de aplicação.",
  ),
  P(
    "8.3. As credenciais de provedores externos são armazenadas cifradas em repouso, por cifra simétrica autenticada, e devolvidas mascaradas nas operações de leitura; as senhas de usuários são armazenadas exclusivamente sob a forma de resumo criptográfico com sal.",
  ),
  P(
    "8.4. O tratamento de dados pessoais observa a Lei nº 13.709/2018, restringindo-se ao mínimo necessário à prestação do serviço, com mascaramento de dados sensíveis conforme o papel institucional do usuário e registro de auditoria das operações relevantes.",
  ),
);

// ---- Cronologia
filhos.push(H1("IX – Do processo de criação e da volumetria da obra"));
filhos.push(
  P(
    "9.1. A criação desenvolveu-se de forma contínua e documentada em sistema de controle de versão, com registro cronológico de cada alteração, sua data, autoria e conteúdo, iniciando-se em 08 de julho de 2026 e alcançando, na versão ora declarada, 28 (vinte e oito) revisões consolidadas, a última datada de 24 de julho de 2026.",
  ),
  P("9.2. A obra apresenta, na versão declarada, a seguinte volumetria de código-fonte:"),
  T(
    [3600, 2100, 2804],
    [
      ["Conjunto", "Arquivos", "Linhas de código"],
      ["Núcleo, API e ingestão (Python)", "146", "8.788"],
      ["Interface web (TSX/React)", "25", "2.463"],
      ["Contratos tipados gerados da especificação OpenAPI e utilitários (TypeScript)", "5", "3.857"],
      ["Infraestrutura declarativa (YAML)", "2", "104"],
      ["Documentação técnica e especificação (Markdown)", "5", "1.130"],
      ["Total de arquivos versionados", "214", "28.431"],
    ],
  ),
  SPACER(140),
  P(
    "9.3. O total geral compreende, além dos conjuntos discriminados, arquivos de configuração, migrações de banco de dados, testes automatizados e ativos da interface.",
    { size: SIZE_SM },
  ),
);

// ---- Originalidade
filhos.push(H1("X – Da originalidade e dos componentes de terceiros"));
filhos.push(
  P(
    "10.1. O AUTOR declara que a concepção, a arquitetura, o modelo de dados, as regras de fusão multifonte, os algoritmos de normalização, deduplicação e detecção de alterações, os conectores, os serviços de negócio e as interfaces do programa constituem criação intelectual própria, original e inédita, não configurando cópia, reprodução, adaptação ou tradução, no todo ou em parte, de obra de terceiro.",
  ),
  P(
    "10.2. O programa emprega, como toda obra de software contemporânea, bibliotecas e arcabouços de terceiros distribuídos sob licenças livres ou abertas, os quais são utilizados na forma e nos limites de suas respectivas licenças, permanecem de titularidade de seus autores e não integram o objeto desta declaração, cujo alcance se restringe ao código original de autoria do declarante e à combinação criativa por ele realizada.",
  ),
  P(
    "10.3. O AUTOR declara que o desenvolvimento não decorreu de contrato de trabalho, de prestação de serviços, de vínculo estatutário ou de encomenda, tampouco se valeu de recursos, informações reservadas, materiais, instalações ou equipamentos de empregador ou contratante, não incidindo, portanto, a hipótese de titularidade derivada prevista no art. 4º da Lei nº 9.609/1998.",
  ),
);

// ---- Titularidade
filhos.push(H1("XI – Da autoria, da titularidade e dos direitos assegurados"));
filhos.push(
  P(
    "11.1. Em razão do exposto, o AUTOR é o único e exclusivo titular dos direitos patrimoniais sobre o programa de computador “HUB CAPTURE”, cabendo-lhe, com exclusividade, os direitos de utilizá-lo, fruí-lo e dispor dele, bem como de reproduzi-lo, editá-lo, licenciá-lo, cedê-lo, comercializá-lo, distribuí-lo, modificá-lo e dele derivar novas versões, no território nacional e no exterior.",
  ),
  P(
    "11.2. São assegurados ao AUTOR, em caráter irrenunciável e inalienável, os direitos morais de reivindicar a paternidade da obra e de opor-se a alterações não autorizadas que impliquem deformação, mutilação ou outra modificação que prejudique sua honra ou reputação, na forma do art. 2º, § 1º, da Lei nº 9.609/1998.",
  ),
  P(
    "11.3. A tutela dos direitos ora declarados independe de registro, nos termos do art. 2º, § 3º, da Lei nº 9.609/1998, sendo o registro e a averbação meios de prova da anterioridade da criação e da titularidade, com prazo de proteção de 50 (cinquenta) anos contados de 1º de janeiro do ano subsequente ao da publicação ou, na sua ausência, da criação, conforme o art. 2º, § 2º, do mesmo diploma.",
  ),
);

// ---- Finalidade
filhos.push(H1("XII – Da finalidade e da destinação deste instrumento"));
filhos.push(
  P(
    "12.1. A presente declaração é firmada para instruir pedido de registro de programa de computador perante o Instituto Nacional da Propriedade Industrial – INPI e/ou para averbação e registro em Cartório de Registro de Títulos e Documentos, servindo como memorial descritivo da criação e como prova da autoria, da titularidade e da data de sua concepção.",
  ),
  P(
    "12.2. O AUTOR declara, sob as penas do art. 299 do Código Penal, serem verdadeiras todas as informações aqui prestadas, assumindo integral responsabilidade civil e penal por seu conteúdo, e autoriza a conferência das informações técnicas mediante exame do código-fonte e do respectivo histórico de versionamento.",
  ),
  P(
    "12.3. Por ser expressão da verdade, firma o presente instrumento, em via única, na presença das testemunhas abaixo identificadas, para que produza seus jurídicos e legais efeitos.",
  ),
);

// ---- Fecho e assinaturas
filhos.push(SPACER(240));
filhos.push(
  PR([{ t: "" }, PH("[Cidade]"), { t: " – " }, PH("[UF]"), { t: ", " }, PH("[dia]"), { t: " de " }, PH("[mês]"), { t: " de " }, PH("[ano]"), { t: "." }], {
    align: AlignmentType.RIGHT,
    after: 240,
  }),
);
filhos.push(...linhaAssinatura("[NOME COMPLETO DO AUTOR] — CPF nº [000.000.000-00]"));
filhos.push(P("Testemunhas:", { bold: true, after: 0, align: AlignmentType.LEFT }));
filhos.push(...linhaAssinatura("1. Nome: [__________________________]  —  CPF nº [________________]"));
filhos.push(...linhaAssinatura("2. Nome: [__________________________]  —  CPF nº [________________]"));

// ---- Anexo I
filhos.push(new Paragraph({ children: [new PageBreak()] }));
filhos.push(H1("Anexo I – Estrutura de módulos do código-fonte"));
filhos.push(
  P(
    "Relação sintética da organização do código-fonte na versão declarada, para conferência do examinador:",
    { size: SIZE_SM },
  ),
  T(
    [3000, 5504],
    [
      ["Diretório", "Conteúdo"],
      ["apps/api/src/core", "Configuração, segurança, autenticação, gestão de usuários e inicialização"],
      ["apps/api/src/db", "Sessão assíncrona, base declarativa e integração com o repositório de usuários"],
      ["apps/api/src/models", "Entidades do modelo relacional (18 entidades)"],
      ["apps/api/src/schemas", "Esquemas de validação de entrada e saída"],
      ["apps/api/src/api/v1", "Roteadores da API pública versionada (17 roteadores)"],
      ["apps/api/src/connectors", "Conectores por fonte governamental (12 módulos), protocolo comum e política compartilhada de acesso HTTP"],
      ["apps/api/src/ingestion", "Normalizadores por entidade e motor de fusão multifonte"],
      ["apps/api/src/services", "Regras de negócio, leitura prioritária em cache, detecção de alterações e despacho de alertas (19 serviços)"],
      ["apps/api/src/ai", "Resumo assistido, geração de vetores de representação e conversação"],
      ["apps/api/src/scraping", "Extração estruturada de páginas públicas"],
      ["apps/api/src/notifications", "Correio eletrônico transacional e mensageria"],
      ["apps/api/src/jobs", "Rotinas assíncronas de processamento em lote"],
      ["apps/api/alembic", "Migrações incrementais do esquema de banco de dados (8 revisões)"],
      ["apps/api/tests", "Testes automatizados de normalização, fusão, cache e isolamento entre assinantes (18 módulos de teste)"],
      ["apps/web/app", "Interface web: autenticação, integração de perfil, painel por dimensão do ciclo e administração (17 páginas)"],
      ["packages/api-client", "Contrato tipado gerado a partir da especificação OpenAPI"],
      ["infra e docker-compose", "Definição declarativa da infraestrutura de execução"],
    ],
  ),
);

// ---- Anexo II
filhos.push(H1("Anexo II – Elementos a completar no ato do depósito"));
filhos.push(
  P("Antes da protocolização, deverão ser conferidos e preenchidos os seguintes elementos:", { size: SIZE_SM }),
  BULLET("qualificação completa do autor e titular, no item I, inclusive número de documento de identidade e endereço;"),
  BULLET("cidade, unidade da federação e data do fecho, bem como assinatura do autor e de duas testemunhas com respectivos números de inscrição no CPF;"),
  BULLET("regeração do resumo digital hash (SHA-512) sobre o arquivo de código-fonte efetivamente depositado, com atualização do valor consignado no item III;"),
  BULLET("preparação do arquivo de código-fonte no formato exigido pelo INPI, contendo as páginas iniciais e finais de cada módulo relevante;"),
  BULLET("recolhimento da retribuição correspondente ao serviço de registro de programa de computador, com a redução aplicável à pessoa física, quando cabível;"),
  BULLET("reconhecimento de firma, se exigido pelo Cartório de Registro de Títulos e Documentos escolhido para a averbação."),
);

/* ------------------------------------------------------------ montagem */

const doc = new Document({
  creator: "Hub Capture",
  title: "Declaração de Autoria e Memorial Descritivo — Hub Capture",
  description: "Documento para averbação e registro de programa de computador",
  numbering: {
    config: [
      {
        reference: "lista",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 260 } } },
          },
        ],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: SIZE } },
    },
  },
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: convertMillimetersToTwip(25),
            bottom: convertMillimetersToTwip(25),
            left: convertMillimetersToTwip(30),
            right: convertMillimetersToTwip(30),
          },
        },
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  children: ["Hub Capture — Declaração de Autoria e Memorial Descritivo — pág. ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES],
                  font: FONT,
                  size: 18,
                  color: "666666",
                }),
              ],
            }),
          ],
        }),
      },
      children: filhos,
    },
  ],
});

const out = process.argv[2] || "averbacao_hub_capture.docx";
Packer.toBuffer(doc).then((buf) => {
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, buf);
  console.log("gerado:", out, buf.length, "bytes");
});
