"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { CriteriosAlerta } from "@/components/CriteriosAlerta";
import { Hint } from "@/components/Hint";
import { AndamentoProposta } from "@/components/AndamentoProposta";
import { EmendasProposta } from "@/components/EmendasProposta";
import { Favorito } from "@/components/Favorito";
import { EmpenhosProposta } from "@/components/EmpenhosProposta";
import { NumeroProposta } from "@/components/NumeroProposta";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { TextoExpansivel } from "@/components/TextoExpansivel";
import { TextoLimitado } from "@/components/TextoLimitado";
import { BotaoVoltar } from "@/components/Voltar";
import { Aviso, Dado, cx } from "@/components/ui";
import {
  diasAte,
  formatBRL,
  formatDate,
  formatDateTime,
  humanizarCaixa,
  municipioPrincipal,
  prazoLabel,
  tomPrazo,
} from "@/lib/format";
import { useTerritorio } from "@/lib/territorio";

type Prazo = { tipo?: string | null; data_limite?: string | null };
type Pendencia = { descricao?: string | null; prazo?: string | null };

type Proposta = {
  id: string;
  fonte: string;
  id_externo: string;
  numero_proposta?: string | null;
  numero_plano_trabalho?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  /** Valor global publicado pela fonte (VL_GLOBAL_PROP) — o card "Empenho". */
  valor_global?: string | null;
  contrapartida?: string | null;
  situacao?: string | null;
  emenda?: string | null;
  prazos?: Prazo[] | null;
  pendencias?: Pendencia[] | null;
  movimentacao?: string | null;
  data_proposta?: string | null;
  data_atualizacao_fonte?: string | null;
  url_origem?: string | null;
  resumo_ia?: string | null;
  /** Pílulas de categoria (curadoria) — slug filtrável + rótulo exibível. */
  categorias?: { slug: string; rotulo: string }[] | null;
  tipo?: string;
  /** Ano de CRIAÇÃO da proposta (ANO_PROP na fonte) — a safra do cabeçalho. */
  ano?: string | null;
  // computados pela API — a tela antes descartava os três
  prazo_final?: string | null;
  dias_restantes?: number | null;
  natureza_juridica?: string | null;
  cache_atualizado_em?: string | null;
  execucao?: {
    valor_global?: string | null;
    valor_empenhado?: string | null;
    valor_liberado?: string | null;
    valor_pago?: string | null;
    /** "Publicado" — a fonte manda ora valor, ora estado; a tela usa os dois. */
    valor_publicado?: string | null;
    situacao_publicacao?: string | null;
    /** dados VIVOS do webapp do SIconv (enriquecimento diário) */
    webapp?: {
      data_ultimo_desembolso?: string | null;
      valor_a_desembolsar?: string | null;
      situacao_siafi?: string | null;
      instrumento?: string | null;
    } | null;
    saldo_conta?: string | null;
    ano?: string | number | null;
    ente_recebedor?: string | null;
    natureza_juridica?: string | null;
    data_assinatura?: string | null;
    data_inicio_vigencia?: string | null;
    data_fim_vigencia?: string | null;
    tipo_transferencia?: string | null;
  } | null;
};

function num(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** De-para situação → tom do badge (mesma disciplina do resto do painel). */
function tomSituacao(situacao?: string | null): BadgeTone {
  const s = (situacao ?? "").toLowerCase();
  if (/aprovad|celebrad|vigente|conclu/.test(s)) return "success";
  if (/pendenc|análise|analise|aguardand|diligenc/.test(s)) return "warning";
  if (/rejeitad|cancelad|impedid|arquivad/.test(s)) return "danger";
  return "neutral";
}

function Secao({
  titulo,
  acao,
  children,
  className,
}: {
  titulo: string;
  /** Controle no canto direito do cabeçalho (ex.: "Ampliar tudo"). */
  acao?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    /* `reveal` (§camada de fluidez): a página do detalhe é a de rolagem mais
       longa do app — cada bloco entra quando chega à viewport, pelo timeline
       de view do navegador (sem JS). Quem não suporta vê o conteúdo direto. */
    <section className={cx("card reveal p-5", className)}>
      <div className="mb-3.5 flex items-center justify-between gap-3 border-b border-hairline pb-2">
        <h2 className="label-mono">{titulo}</h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

function Carregando() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-36 w-full" />
      <div className="grid gap-5 md:grid-cols-2">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    </div>
  );
}

export default function PropostaDetalhePage() {
  const params = useParams<{ id: string }>();
  // módulos efetivos do perfil — decide se a seção de pareceres (exploração
  // ao vivo do módulo captação) aparece; o detalhe em si é panel-core (§40)
  const { perfil, carregando: perfilCarregando } = useTerritorio();
  // §40: o detalhe é panel-core; o módulo captação governa só a consulta ATIVA
  // às fontes (o botão "Consultar fonte" das seções de andamento e emenda).
  const podeExplorar = (perfil?.modulos ?? []).includes("captacao");
  // VOLTAR: com o módulo captação desligado, a lista de propostas não existe
  // para este usuário — devolvê-lo a ela é jogá-lo no ModuloGate ("este módulo
  // está desativado"), um beco. O retorno natural passa a ser o Meu painel, que
  // é panel-core como o próprio detalhe. Enquanto o perfil carrega mantemos a
  // captação: é de onde a maioria chega, e o gate ainda cobre o caso raro.
  const voltarParaPainel = !perfilCarregando && !podeExplorar;
  const voltarHref = voltarParaPainel ? "/panel" : "/panel/funding";
  const voltarRotulo = voltarParaPainel ? "Meu painel" : "Propostas";
  const [p, setP] = useState<Proposta | null>(null);
  const [resumoEmpenhos, setResumoEmpenhos] = useState<{
    valor_empenhado?: string | null;
    valor_pago?: string | null;
  } | null>(null);
  useEffect(() => {
    if (!params.id) return;
    void (async () => {
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/commitments", {
        params: { path: { proposta_id: params.id } },
      });
      const r = (
        data as {
          resumo?: { valor_empenhado?: string | null; valor_pago?: string | null };
        }
      )?.resumo;
      if (r) setResumoEmpenhos(r);
    })();
  }, [params.id]);
  const [erro, setErro] = useState<string | null>(null);
  const [favorita, setFavorita] = useState(false);
  // monitoramento da proposta: guarda o id e os CRITÉRIOS escolhidos (§53) —
  // é por eles que o usuário decide o que quer ser avisado
  const [monitor, setMonitor] = useState<{
    id: string;
    criterios: string[] | null;
  } | null>(null);
  const [configurando, setConfigurando] = useState(false);
  // Aviso da tela com TOM: os erros (favorita que não salvou, PDF que falhou)
  // não podem sair pintados de verde como se fossem sucesso.
  const [msg, setMsg] = useState<{ tom: "ok" | "erro"; texto: string } | null>(
    null,
  );

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/proposals/{proposta_id}", {
        params: { path: { proposta_id: params.id } },
      });
      if (error) {
        setErro("Proposta não encontrada (ou fora do seu território).");
        return;
      }
      setP(data as Proposta);
      const [fav, mon] = await Promise.all([
        api.GET("/api/v1/favorites"),
        api.GET("/api/v1/monitors"),
      ]);
      if (fav.data)
        setFavorita(
          (fav.data as { proposta_id: string }[]).some(
            (f) => f.proposta_id === params.id,
          ),
        );
      if (mon.data) {
        const meu = (
          mon.data as {
            id: string;
            proposta_id: string;
            ativo: boolean;
            criterios?: string[] | null;
          }[]
        ).find((m) => m.proposta_id === params.id && m.ativo);
        setMonitor(meu ? { id: meu.id, criterios: meu.criterios ?? null } : null);
      }
    })();
  }, [params.id]);

  async function alternarFavorito() {
    const proximo = !favorita;
    setFavorita(proximo); // otimista — a estrela responde na hora
    const { error } = proximo
      ? await api.POST("/api/v1/favorites", { body: { proposta_id: params.id } })
      : await api.DELETE("/api/v1/favorites/{proposta_id}", {
          params: { path: { proposta_id: params.id } },
        });
    if (error) {
      // desfaz E avisa — o rollback mudo lia como "favoritei e não persistiu"
      setFavorita(!proximo);
      setMsg({
        tom: "erro",
        texto: proximo
          ? "Não foi possível favoritar agora — tente novamente."
          : "Não foi possível remover a favorita agora — tente novamente.",
      });
    }
  }

  async function monitorar() {
    const { data, error } = await api.POST("/api/v1/monitors", {
      // canal painel: os demais (e-mail/WhatsApp) são escolhidos na central
      // de Alertas, onde o usuário configura o monitoramento por município.
      // criterios ausente = padrões do catálogo (avisa tudo) — o multi-select
      // logo abaixo é que apara o que não interessa.
      body: { proposta_id: params.id, canais: ["painel"] },
    });
    if (!error) {
      const criado = data as { id?: string } | undefined;
      if (criado?.id) setMonitor({ id: criado.id, criterios: null });
      setConfigurando(true);
      setMsg({
        tom: "ok",
        texto:
          "Monitorando. Escolha abaixo quais alterações devem virar alerta.",
      });
    }
  }

  /** Reconfigura os critérios (o POST é upsert — não há PATCH de monitoramento). */
  async function salvarCriterios(criterios: string[]) {
    setMonitor((prev) => (prev ? { ...prev, criterios } : prev));
    const { error } = await api.POST("/api/v1/monitors", {
      body: { proposta_id: params.id, canais: ["painel"], criterios },
    });
    if (error)
      setMsg({
        tom: "erro",
        texto: "Não foi possível salvar os critérios agora — tente novamente.",
      });
  }

  async function pararMonitoramento() {
    if (!monitor) return;
    const { error } = await api.DELETE("/api/v1/monitors/{monitoramento_id}", {
      params: { path: { monitoramento_id: monitor.id } },
    });
    if (!error) {
      setMonitor(null);
      setConfigurando(false);
      setMsg({ tom: "ok", texto: "Monitoramento encerrado." });
    }
  }

  if (erro) {
    return (
      <div className="flex flex-col items-start gap-4">
        <Aviso tom="erro">{erro}</Aviso>
        <BotaoVoltar href={voltarHref} rotulo={voltarRotulo} />
      </div>
    );
  }
  if (!p) return <Carregando />;

  // Ano da proposta (safra): o computado pela API (ANO_PROP na fonte), com
  // retaguarda no ano da data de criação já ingerida.
  const anoProposta = p.ano ?? (p.data_proposta ? p.data_proposta.slice(0, 4) : null);
  const disponivel = p.tipo === "disponivel";
  // EMPENHO na faixa de destaque = VL_GLOBAL_PROP, o valor global que a fonte
  // publica para a proposta (a API resolve o campo cru e devolve em
  // `valor_global`). A conta derivada "empenhado − pago" saiu da tela: nas
  // propostas ela dava zero e não dizia nada ao gestor.
  const valorGlobal = p.valor_global ?? p.execucao?.valor_global ?? null;
  const temValorGlobal = num(valorGlobal) > 0;
  // O empenhado é o que a fonte publica como EMPENHADO — nunca o valor global
  // (que é o total previsto da proposta). Quando a fonte não informa, o card
  // fica vazio de propósito: a seção "Empenhos" abaixo soma os documentos.
  // Retaguarda dos DOCUMENTOS: o agregado da execução vem do pacote/painel da
  // fonte (~mensal); empenho recém-emitido só existe na soma das notas (a
  // mesma da seção "Empenhos"). Sem ela o header dizia "sem empenho" com a
  // nota de R$ 390 mil listada logo abaixo.
  const valorEmpenhado =
    p.execucao?.valor_empenhado ?? resumoEmpenhos?.valor_empenhado ?? null;
  const temEmpenhado = num(valorEmpenhado) > 0;
  const valorPago = p.execucao?.valor_pago ?? resumoEmpenhos?.valor_pago ?? null;

  return (
    <div className="flex flex-col gap-5">
      {/* ── CABEÇALHO EM TRÊS FAIXAS ─────────────────────────────────
          O header vinha como uma pilha de linhas soltas do mesmo peso —
          número, data, órgão, badge e pílulas de categoria empilhados sem
          divisão, com o objeto em corpo de título disputando com o município.
          Agora são faixas com papéis distintos:
            1. navegação + ações (a barra de contexto da página);
            2. identidade — MUNICÍPIO (§35) + estado da proposta + objeto;
            3. referência — nº, data, órgão e categorias, em tipografia de
               apoio, separadas por hairline.                              */}
      <header className="flex flex-col gap-4 border-b border-hairline pb-5">
        {/* ── 1. Barra de contexto: retorno à esquerda, ações à direita ─ */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          {/* O retorno é a pílula padrão (BotaoVoltar) — o link mono de 11px
              que ficava aqui era quase invisível. */}
          <BotaoVoltar href={voltarHref} rotulo={voltarRotulo} />
          {/* Ações agrupadas — nunca um botão grande solto no canto. Subiram
              para a barra de contexto: no bloco de identidade competiam com o
              título e, ao quebrar a linha, viravam uma quarta pilha. */}
          {/* `shrink-0` aqui causava ROLAGEM HORIZONTAL da página abaixo de
              ~375px: o grupo se recusava a encolher e o "Espelho PDF" saía
              pela borda. Sem ele, os botões quebram entre si; largura cheia
              no mobile (o retorno fica sozinho na 1ª linha) e alinhados à
              direita a partir do sm, onde tudo cabe ao lado do "voltar". */}
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
            <Favorito
              ativo={favorita}
              onToggle={alternarFavorito}
              comRotulo
              tamanho={15}
              className="fav-solid h-8"
            />
            {/* O quadro "Acompanhar e ser avisado" saiu (ponto 17), mas monitorar
                não podia sair com ele: vira ação do cabeçalho, no canal painel.
                Os demais canais seguem na central de Alertas. */}
            <button
              onClick={monitor ? () => setConfigurando((v) => !v) : monitorar}
              aria-pressed={Boolean(monitor)}
              title={
                monitor
                  ? "Escolher quais alterações devem virar alerta"
                  : "Avisar quando algo mudar nesta proposta"
              }
              className={cx("btn btn-sm", monitor ? "btn-accent" : "btn-solid")}
            >
              {monitor ? "🔔 Monitorando" : "🔔 Monitorar"}
            </button>
            {/* atalho "P": o gestor exporta sem tirar a mão do teclado */}
            <BotaoEspelho
              propostaId={params.id}
              atalho="p"
              onResultado={(texto, tom) => setMsg({ tom, texto })}
            />
            {/* O link "Fonte oficial ↗" SAIU do cabeçalho: mandava o gestor
                para FORA da plataforma para ver o que a página já mostra
                (dados gerais, situação, prazos, execução e andamento). O
                `url_origem` continua no registro (a API segue devolvendo),
                só não é mais uma porta de saída no alto da página. */}
          </div>
        </div>

        {/* ── 2. Identidade ────────────────────────────────────────────
            Hierarquia (§35): MUNICÍPIO → objeto → números → identificadores.
            O município é a identidade do registro, então encabeça o header; o
            código IBGE desce para linha de apoio e o id da fonte sai daqui.
            O estado da proposta acompanha o título NA MESMA LINHA — sozinho
            numa linha própria ele virava só mais um degrau da pilha. */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <h1 className="page-title">{municipioPrincipal(p)}</h1>
            <StatusBadge tone={disponivel ? "success" : "neutral"}>
              {disponivel ? "oportunidade disponível" : "cadastrada"}
            </StatusBadge>
          </div>
          {/* O objeto da proposta vem logo abaixo — nunca um identificador:
              antes o h1 caía para `id_externo` quando faltava título.
              Corpo de TEXTO, não de título: em `text-lg font-semibold` ele
              disputava com o município e empurrava o resto para fora da dobra.
              Com TETO de caracteres, porque a fonte não separa título de
              descrição — o inteiro abre em janela. */}
          <p className="mt-2 max-w-[68ch] text-[0.9375rem] leading-relaxed text-ink-2">
            <TextoLimitado
              texto={humanizarCaixa(p.titulo ?? p.objeto)}
              limite={150}
              titulo={municipioPrincipal(p)}
              rotulo="Objeto da proposta"
              vazio={
                <span className="text-ink-3">Proposta sem título na fonte</span>
              }
            />
          </p>
        </div>

        {/* ── 3. Referência ────────────────────────────────────────────
            Nº da proposta, data de criação e órgão concedente: é assim que o
            gestor se refere a ela ("14275/2026, de 26/03") e é o que ele digita
            para conferir no portal da fonte. Dado de cabeçalho — diferente de
            `id_externo`/UUID, que são plumbing e ficam em "Dados gerais".
            Uma faixa só, com separadores, em vez de três linhas empilhadas.
            A FONTE não entra aqui: é detalhe de ingestão, não identidade do
            registro (§19). */}
        <div className="meta-strip flex flex-wrap items-center gap-x-2 gap-y-2 border-t border-hairline pt-3 text-sm text-ink-2">
          {/* nº + ⓘ são UM item da faixa: o ⓘ explica o número, não é um
              metadado à parte, e assim não ganha separador entre os dois. */}
          <span className="inline-flex items-center gap-2">
            {p.numero_proposta ? (
              // mesma pílula da lista e do feed: o gestor reconhece o número
              // pelo formato e daqui copia para colar no portal da fonte
              <NumeroProposta numero={p.numero_proposta} />
            ) : (
              <span>
                Proposta <span className="num text-ink-3">sem nº na fonte</span>
              </span>
            )}
            <Hint chave="proposta.numero_proposta" className="align-middle" />
          </span>
          {p.data_proposta && (
            <span>
              criada em{" "}
              <span className="num text-ink">{formatDate(p.data_proposta)}</span>
            </span>
          )}
          {/* No mobile o órgão QUEBRA em vez de truncar: sem cursor não há
              tooltip, então o `title` não devolveria o que a reticência come.
              Do sm para cima ele trunca e a faixa continua numa linha só. */}
          {p.orgao_superior && (
            <span className="min-w-0 sm:truncate" title={humanizarCaixa(p.orgao_superior)}>
              {humanizarCaixa(p.orgao_superior)}
            </span>
          )}
          {/* pílulas de categoria (curadoria) — do que esta proposta trata.
              Encostadas à direita: são etiqueta do registro, não continuação
              da referência, e assim a faixa não vira uma segunda pilha. */}
          {(p.categorias ?? []).length > 0 && (
            /* `sm:ml-auto` saiu: quando a faixa quebrava, os chips iam
               parar sozinhos à direita de uma linha vazia, descolados do
               registro. Fluindo, eles fecham a faixa onde ela terminar. */
            <div className="meta-sem-sep flex flex-wrap items-center gap-1.5">
              {p.categorias!.map((c) => (
                <span
                  key={c.slug}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-ink-2"
                >
                  <span className="brand-dot" aria-hidden />
                  {c.rotulo}
                </span>
              ))}
            </div>
          )}
        </div>
      </header>

      {msg && <Aviso tom={msg.tom}>{msg.texto}</Aviso>}

      {/* Critérios do alerta: monitorar deixou de ser tudo-ou-nada (§53) */}
      {monitor && configurando && (
        <section className="card flex flex-col gap-3 p-4">
          <CriteriosAlerta
            escopo="proposta"
            valor={monitor.criterios}
            onChange={salvarCriterios}
            descricao="Só o que estiver marcado vira alerta desta proposta. A escolha vale para painel, e-mail e WhatsApp."
          />
          <div className="flex justify-end">
            <button onClick={pararMonitoramento} className="btn btn-ghost btn-sm">
              Parar de monitorar
            </button>
          </div>
        </section>
      )}

      {/* ── FAIXA DE DESTAQUE ────────────────────────────────────────
          O topo da hierarquia: valor, empenho e a SAFRA da proposta
          (ano de criação na fonte). Tudo o mais é subordinado. */}
      {/* Dois degraus DENTRO da faixa: valor/empenho/ano ocupam a linha de
          cima inteira; o resto desce um nível. Quatro colunas de peso igual
          não cabiam — os números colidiam. */}
      <section className="hero-band anim-page-delayed">
        <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
          <div className="field">
            <span className="field-label">
              Valor total <Hint chave="proposta.valor_total" />
            </span>
            <span className="value-hero">{formatBRL(p.valor_total)}</span>
            {p.contrapartida && num(p.contrapartida) > 0 && (
              <span className="num mt-1 text-xs text-ink-3">
                contrapartida <Hint chave="proposta.contrapartida" className="mr-1 align-middle" />
                {formatBRL(p.contrapartida)}
              </span>
            )}
          </div>

          {/* EMPENHADO — o valor que a fonte informa como empenhado, e só ele.
              Este card já mostrou o VALOR GLOBAL da proposta com o rótulo
              "Empenho": dava o mesmo número do "Valor total" ao lado e fazia o
              gestor ler como reservado o que ainda era só previsto. O valor
              global não sumiu: está logo abaixo, com o nome dele. */}
          <div className="field">
            <span className="field-label">
              Empenhado <Hint chave="proposta.empenhado" />
            </span>
            {temEmpenhado ? (
              <>
                <span className="value-hero">{formatBRL(valorEmpenhado)}</span>
                <span className="num mt-1 text-xs text-ink-3">
                  reservado pelo concedente
                </span>
              </>
            ) : (
              <>
                <span className="value-hero text-ink-3">—</span>
                <span className="num mt-1 text-xs text-ink-3">
                  sem empenho informado na fonte
                </span>
              </>
            )}
          </div>

          {/* PUBLICADO (ponto 13). A fonte usa o termo nos dois sentidos: o
              valor publicado do convênio e o estado da publicação no DOU. O
              valor manda quando existe; senão vale o estado, que ainda é a
              resposta que o gestor procura ("saiu ou não saiu?"). */}
          <div className="field">
            <span className="field-label">Publicado</span>
            {num(p.execucao?.valor_publicado) > 0 ? (
              <>
                <span className="value-hero">
                  {formatBRL(p.execucao!.valor_publicado)}
                </span>
                <span className="num mt-1 text-xs text-ink-3">
                  valor publicado na fonte
                </span>
              </>
            ) : p.execucao?.situacao_publicacao ? (
              <>
                <span className="value-lg">
                  {humanizarCaixa(String(p.execucao.situacao_publicacao))}
                </span>
                <span className="num mt-1 text-xs text-ink-3">
                  situação da publicação
                </span>
              </>
            ) : (
              <>
                <span className="value-hero text-ink-3">—</span>
                <span className="num mt-1 text-xs text-ink-3">
                  sem publicação informada na fonte
                </span>
              </>
            )}
          </div>

          {/* PAGO subiu da seção de execução financeira (ponto 13): é o que
              responde "o recurso chegou?", e o gestor lia isso só depois de
              rolar a página inteira. */}
          <div className="field">
            <span className="field-label">Pago</span>
            {num(valorPago) > 0 ? (
              <>
                <span className="value-hero">{formatBRL(valorPago)}</span>
                <span className="num mt-1 text-xs text-ink-3">
                  {p.execucao?.webapp?.data_ultimo_desembolso
                    ? `último desembolso em ${p.execucao.webapp.data_ultimo_desembolso}`
                    : "efetivamente pago ao ente"}
                </span>
              </>
            ) : (
              <>
                <span className="value-hero text-ink-3">—</span>
                <span className="num mt-1 text-xs text-ink-3">
                  nada pago até agora
                </span>
              </>
            )}
          </div>

        </div>

        <hr className="hairline-rule" />

        <div className="data-grid">
          <div className="field">
            <span className="field-label">
              Situação <Hint chave="proposta.situacao" />
            </span>
            <span className="mt-0.5">
              <StatusBadge tone={tomSituacao(p.situacao)}>
                {humanizarCaixa(p.situacao) || "sem registro"}
              </StatusBadge>
            </span>
          </div>

          <Dado
            rotulo={
              <>
                Pendências <Hint chave="proposta.pendencias" />
              </>
            }
            valor={
              (p.pendencias ?? []).length === 0
                ? "nenhuma"
                : `${(p.pendencias ?? []).length} a resolver`
            }
            tom={(p.pendencias ?? []).length > 0 ? "warn" : "ok"}
            destaque
          />

          <Dado
            rotulo={
              <>
                Modalidade <Hint chave="proposta.modalidade" />
              </>
            }
            valor={humanizarCaixa(p.modalidade)}
            destaque
          />

          {temValorGlobal && (
            <Dado
              rotulo="Valor global da proposta"
              valor={formatBRL(valorGlobal)}
              destaque
            />
          )}

          <Dado
            rotulo={
              <>
                Ano da proposta <Hint chave="proposta.ano" />
              </>
            }
            valor={
              anoProposta
                ? p.data_proposta
                  ? `${anoProposta} · criada em ${formatDate(p.data_proposta)}`
                  : anoProposta
                : null
            }
            destaque
          />
        </div>
      </section>

      {p.resumo_ia && (
        <Secao titulo="Resumo inteligente">
          <p className="text-sm leading-relaxed text-ink-2">{p.resumo_ia}</p>
        </Secao>
      )}

      {/* ── Prazos e pendências: segundo degrau, largura inteira ────── */}
      <div className="stagger grid gap-5 md:grid-cols-2">
        {/* o ⓘ do prazo mora aqui agora — o cabeçalho mostra a safra */}
        <Secao titulo="Prazos" acao={<Hint chave="proposta.prazo" />}>
          {(p.prazos ?? []).length === 0 ? (
            <p className="text-sm text-ink-3">Sem prazos registrados.</p>
          ) : (
            <ul>
              {p.prazos!.map((pr, i) => {
                const d = diasAte(pr.data_limite);
                const tom = tomPrazo(d);
                return (
                  <li key={i} className="data-row">
                    <span className="text-sm">{humanizarCaixa(pr.tipo) || "prazo"}</span>
                    <span className="flex shrink-0 items-baseline gap-2">
                      <span className={cx("num text-sm", tom && `tone-${tom}`)}>
                        {formatDate(pr.data_limite)}
                      </span>
                      <span
                        className={cx(
                          "font-mono text-[11px] uppercase tracking-[0.04em]",
                          tom ? `tone-${tom}` : "text-ink-3",
                        )}
                      >
                        {prazoLabel(pr.data_limite)}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Secao>

        <Secao titulo="Pendências">
          {(p.pendencias ?? []).length === 0 ? (
            <p className="tone-ok text-sm">✓ Sem pendências.</p>
          ) : (
            <ul>
              {p.pendencias!.map((pe, i) => {
                const d = diasAte(pe.prazo);
                const tom = tomPrazo(d);
                return (
                  <li key={i} className="data-row">
                    <span className="text-sm">{humanizarCaixa(pe.descricao) || "—"}</span>
                    {pe.prazo && (
                      <span className={cx("num shrink-0 text-sm", tom && `tone-${tom}`)}>
                        {formatDate(pe.prazo)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Secao>
      </div>

      <div className="stagger grid gap-5 md:grid-cols-2">
        <Secao titulo="Dados gerais">
          <div className="data-grid">
            {/* Município nomeado; o código IBGE aparece rotulado logo abaixo,
                como apoio — antes este campo mostrava só o número. */}
            <Dado rotulo="Município" valor={municipioPrincipal(p)} />
            <Dado rotulo="Código IBGE" valor={p.municipio_ibge} />
            <Dado rotulo="Órgão superior" valor={humanizarCaixa(p.orgao_superior)} />
            <Dado rotulo="Modalidade" valor={humanizarCaixa(p.modalidade)} />
            <Dado rotulo="Emenda" valor={p.emenda} />
            <Dado rotulo="Natureza jurídica" valor={p.natureza_juridica} />
            {/* SÓ o NR_PROPOSTA. A retaguarda para `id_externo` fazia o campo
                exibir o identificador da integração ROTULADO como "nº da
                proposta" — um número que não existe no portal da fonte e que o
                gestor levaria para a conversa com o órgão. Sem número o campo
                fica vazio ("—"), honesto; o id da fonte tem a linha logo abaixo. */}
            <Dado rotulo="Nº da proposta" valor={p.numero_proposta} />
            <Dado rotulo="Identificador na fonte" valor={p.id_externo} />
            <Dado
              rotulo="Criada na fonte"
              valor={formatDate(p.data_proposta)}
            />
            <Dado
              rotulo="Atualizado na fonte"
              valor={formatDate(p.data_atualizacao_fonte)}
            />
            <Dado
              rotulo="Cache atualizado"
              valor={formatDateTime(p.cache_atualizado_em)}
            />
          </div>
          {/* Vindos da antiga seção "Execução financeira" (ponto 13): o quadro
              saiu da tela, mas liberado, saldo, vigências e ente recebedor
              seguem sendo dado da proposta — só mudaram de lugar. */}
          {p.execucao && (
            <>
              <hr className="hairline-rule my-4" />
              <div className="data-grid">
                <Dado
                  rotulo="Liberado"
                  valor={formatBRL(p.execucao.valor_liberado)}
                />
                <Dado
                  rotulo="Saldo em conta"
                  valor={formatBRL(p.execucao.saldo_conta)}
                />
                <Dado
                  rotulo="Ente recebedor"
                  valor={humanizarCaixa(p.execucao.ente_recebedor)}
                />
                <Dado
                  rotulo="Tipo de transferência"
                  valor={humanizarCaixa(p.execucao.tipo_transferencia)}
                />
                <Dado
                  rotulo="Assinatura"
                  valor={formatDate(p.execucao.data_assinatura)}
                />
                <Dado
                  rotulo="Início da vigência"
                  valor={formatDate(p.execucao.data_inicio_vigencia)}
                />
                <Dado
                  rotulo="Fim da vigência"
                  valor={formatDate(p.execucao.data_fim_vigencia)}
                  tom={tomPrazo(diasAte(p.execucao.data_fim_vigencia))}
                />
              </div>
            </>
          )}
          {p.objeto && (
            <>
              <hr className="hairline-rule my-4" />
              <div className="field">
                <span className="field-label">Objeto</span>
                {/* o objeto é o outro campo de extensão livre da fonte */}
                <TextoExpansivel texto={humanizarCaixa(p.objeto)} linhas={4} />
              </div>
            </>
          )}
        </Secao>

        <Secao titulo="Situação e movimentação">
          <div className="flex flex-col gap-4">
            <div className="field">
              <span className="field-label">Situação</span>
              <span className="value-lg">{humanizarCaixa(p.situacao) || "—"}</span>
            </div>
            <div className="field">
              <span className="field-label">Última movimentação</span>
              {p.movimentacao ? (
                <TextoExpansivel texto={humanizarCaixa(p.movimentacao)} linhas={4} />
              ) : (
                <p className="text-sm leading-relaxed text-ink-3">
                  Sem movimentação registrada.
                </p>
              )}
            </div>
          </div>
        </Secao>
      </div>

      {/* Andamento e emenda são leitura de CACHE (panel-core, §40) — ficam na
          tela mesmo com a captação desligada. O que o módulo governa é a
          consulta AO VIVO, então só o botão "Consultar fonte" depende dele. */}
      <AndamentoProposta proposta={p} podeConsultarFonte={podeExplorar} />

      <EmpenhosProposta proposta={p} podeConsultarFonte={podeExplorar} />

      <EmendasProposta proposta={p} podeConsultarFonte={podeExplorar} />
    </div>
  );
}
