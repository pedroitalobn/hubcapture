"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, baixarCsv } from "@/lib/api/client";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { Favorito } from "@/components/Favorito";
import { Hint } from "@/components/Hint";
import { ModuloGate } from "@/components/ModuloGate";
import { NumeroProposta } from "@/components/NumeroProposta";
import { PageHeader } from "@/components/PageHeader";
import { IconeAcao, IconeNav } from "@/components/icons";
import { ItemMenu, Seletor, SeletorSimples } from "@/components/kit";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { TextoLimitado } from "@/components/TextoLimitado";
import {
  formatBRL,
  formatBRLCompact,
  formatDate,
  formatDateTime,
  haQuantoTempo,
  humanizarCaixa,
  municipioPrincipal,
  municipioSecundario,
} from "@/lib/format";
import { rotuloFonte } from "@/lib/fontes";
import { paramFonte, useOrigem } from "@/lib/origem";
import { paramMunicipio, rotuloMunicipio, useTerritorio } from "@/lib/territorio";
import { cx } from "@/components/ui";

// mapeia a situação da proposta para o tom do badge (verde = bom andamento,
// âmbar = em análise/pendente, vermelho = negado/cancelado)
function tomSituacao(s?: string | null): BadgeTone {
  const t = (s ?? "").toLowerCase();
  if (/autoriz|aprov|execu|pago|libera|conclu|vigente|celebrad|recebid/.test(t))
    return "success";
  if (/cancel|rejeit|indefer|reprov|inadimpl|impedid|vencid|expirad/.test(t))
    return "danger";
  if (/analis|pendente|aguard|cadastr|propost|elabor|em andamento/.test(t))
    return "warning";
  return "neutral";
}

type Proposta = {
  id: string;
  id_externo: string;
  numero_proposta?: string | null;
  data_proposta?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
  tipo?: string;
  natureza_juridica?: string | null;
  /** Ano de CRIAÇÃO da proposta (ANO_PROP na fonte) — a safra da coluna "Ano". */
  ano?: string | null;
  // o prazo continua vindo da API (e no banco); só não é mais exibido na lista
  prazo_final?: string | null;
  dias_restantes?: number | null;
  resumo_ia?: string | null;
  categorias?: { slug: string; rotulo: string }[] | null;
  execucao?: {
    valor_global?: string | null;
    valor_empenhado?: string | null;
    valor_liberado?: string | null;
    valor_pago?: string | null;
    saldo_conta?: string | null;
    ano?: string | number | null;
  } | null;
};

type FonteStatus = {
  fonte: string;
  municipio_ibge: string;
  // "ok" = consultada agora · "erro" = fonte falhou · "cache" = não foi
  // consultada (o dado ainda estava fresco). O terceiro estado existe para a
  // tela não anunciar consulta que não houve.
  status: string;
  erro?: string | null;
  registros?: number | null;
};

type Opcao = { valor: string; rotulo: string; total: number };
type Facetas = {
  municipio?: Opcao[];
  uf?: Opcao[];
  fonte?: Opcao[];
  modalidade?: Opcao[];
  orgao?: Opcao[];
  situacao?: Opcao[];
  natureza_juridica?: Opcao[];
  natureza_grupo?: Opcao[];
  qualificacao?: Opcao[];
  categoria?: Opcao[];
  ano?: Opcao[];
  mes?: Opcao[];
  tipo?: Opcao[];
};

type Pasta = { id: string; nome: string; cor?: string | null };

// O município NÃO é filtro desta tela: quais dos municípios do perfil entram
// no painel é escolha global (barra de filtros, `lib/territorio`), válida para
// todas as lentes. Aqui só se lê o recorte ativo.
type Filtros = {
  uf: string;
  ano: string;
  mes: string;
  tipo: "" | "cadastrada" | "disponivel";
  area: string;
  categoria: string;
  situacao: string;
  q: string;
  modalidade: string;
  orgao: string;
  naturezaJuridica: string;
  naturezaGrupo: string;
  qualificacao: string;
  ordenar: string;
  valorMin: string;
  valorMax: string;
  soFavoritas: boolean;
  pastaId: string;
};

type Aba = { id: string; nome: string; filtros: Filtros };

const FILTROS_VAZIOS: Filtros = {
  uf: "",
  ano: "",
  mes: "",
  tipo: "",
  area: "",
  categoria: "",
  situacao: "",
  q: "",
  modalidade: "",
  orgao: "",
  naturezaJuridica: "",
  naturezaGrupo: "",
  qualificacao: "",
  ordenar: "recentes",
  valorMin: "",
  valorMax: "",
  soFavoritas: false,
  pastaId: "",
};

const AREAS = [
  "saude",
  "educacao",
  "infraestrutura",
  "assistencia_social",
  "cultura",
  "esporte",
  "meio_ambiente",
  "agricultura",
];

// Quem pode propor — os botões de natureza jurídica elegível. Os slugs vêm do
// classificador do backend (`services/propostas.classificar_natureza_juridica`).
const NATUREZAS: [string, string][] = [
  ["", "Todas"],
  ["estadual_df", "Adm. Pública Estadual/DF"],
  ["municipal", "Adm. Pública Municipal"],
  ["consorcio", "Consórcio Público"],
  ["empresa_publica", "Empresa pública / economia mista"],
  ["osc", "Organização da Sociedade Civil"],
];

// As duas LENTES de natureza jurídica (§ produto): a consulta parte daqui —
// quem propõe é o município ou é outro. Os slugs detalhados de NATUREZAS
// continuam no filtro avançado, para quem quiser refinar.
const LENTES_NATUREZA: [string, string][] = [
  ["", "Todas"],
  ["entes_municipais", "Entes municipais"],
  ["outros", "Outros"],
];

// Ordenar por prazo saiu da UI junto com a coluna: ordenava por fim de
// vigência, que não é prazo de proposta. A API mantém `ordenar=prazo`
// (e `prazo_distante`) para quem consome o contrato direto.
const ORDENACOES: [string, string][] = [
  ["recentes", "Mais recentes"],
  ["nome", "Nome A-Z"],
  ["orgao", "Órgão A-Z"],
  ["valor", "Maior valor"],
];

const ABAS_KEY = "hub_captacao_abas";
const ABA_ACOMPANHAMENTO = "acompanhamento";

// ── Paginação da lista ──────────────────────────────────────────────────────
// A tela lê do BANCO, de página em página. Antes ela chamava
// `/proposals/live-search` a CADA carregamento: isso coletava nas fontes ao
// vivo (uma delas baixa um CSV de ~1 GB) e devolvia as milhares de propostas de
// uma vez só. A coleta virou a ação explícita "Atualizar fontes" — e o worker
// faz o sweep diário, então a lista não envelhece por isso.
const POR_PAGINA_KEY = "hub_captacao_por_pagina";
const POR_PAGINA_OPCOES = [10, 30, 50, 100];
const POR_PAGINA_PADRAO = 30;

/** Preferência salva de itens por vez; null quando não há uma utilizável. */
function lerPorPaginaSalvo(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const salvo = Number(window.localStorage.getItem(POR_PAGINA_KEY));
    return POR_PAGINA_OPCOES.includes(salvo) ? salvo : null;
  } catch {
    return null; // preferência corrompida/bloqueada → volta ao padrão
  }
}

function num(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

function abasIniciais(): Aba[] {
  if (typeof window !== "undefined") {
    try {
      const salvo = window.localStorage.getItem(ABAS_KEY);
      if (salvo) {
        const abas = JSON.parse(salvo) as Aba[];
        // Reescreve pelas chaves de HOJE: completa filtros novos e descarta os
        // que saíram (o município virou seleção global de território).
        return abas.map((a) => {
          const salvos = (a.filtros ?? {}) as Record<string, unknown>;
          const filtros = Object.fromEntries(
            Object.entries(FILTROS_VAZIOS).map(([k, padrao]) => [
              k,
              salvos[k] ?? padrao,
            ]),
          ) as Filtros;
          return { ...a, filtros };
        });
      }
    } catch {
      /* estado corrompido → recomeça */
    }
  }
  return [{ id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } }];
}

/** Seletor alimentado por faceta: só mostra o que EXISTE no recorte, com
 *  contagem. Usa o kit do painel (`components/kit`) em vez de um `<select>`
 *  nativo — o mesmo gatilho e o mesmo menu do recorte global, então os filtros
 *  da tela e os da barra de cima se parecem e se operam igual. O nativo ainda
 *  escondia a contagem atrás do clique e não tinha busca: com quarenta órgãos
 *  na lista, achar o certo era rolar no escuro. */
function SelectFaceta({
  rotulo,
  valor,
  opcoes,
  largura,
  aoMudar,
}: {
  rotulo: string;
  valor: string;
  opcoes?: Opcao[];
  /** Largura MÍNIMA do menu, em unidade CSS (o gatilho se ajusta ao valor). */
  largura: string;
  aoMudar: (v: string) => void;
}) {
  const lista = opcoes ?? [];
  const [busca, setBusca] = useState("");
  const escolhida = lista.find((o) => o.valor === valor);
  // Sem nenhuma opção e sem escolha o filtro não filtra: fica inerte, com o
  // mesmo tamanho, para a barra não dançar quando o recorte muda.
  const inerte = lista.length === 0 && !valor;
  const filtradas = busca.trim()
    ? lista.filter((o) =>
        o.rotulo.toLowerCase().includes(busca.trim().toLowerCase()),
      )
    : lista;

  if (inerte) {
    return (
      <span className="trigger opacity-50" style={{ minWidth: largura }}>
        <span className="trigger-txt">
          <span className="trigger-label">{rotulo}</span>
          <span className="trigger-value text-ink-3">todas</span>
        </span>
      </span>
    );
  }

  return (
    <Seletor
      rotulo={rotulo}
      valor={escolhida?.rotulo ?? valor ?? "todas"}
      ativo={Boolean(valor)}
      largura={largura}
    >
      {(fechar) => (
        <>
          {lista.length >= 8 && (
            <div className="menu-head">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder={`Filtrar ${rotulo.toLowerCase()}…`}
                className="input w-full text-sm"
                autoFocus
              />
            </div>
          )}
          <ItemMenu
            marcado={!valor}
            radio
            rotulo="Todas"
            onClick={() => {
              aoMudar("");
              fechar();
            }}
          />
          <div className="menu-sep" />
          <div className="menu-scroll" role="listbox" aria-label={rotulo}>
            {filtradas.map((o) => (
              <ItemMenu
                key={o.valor}
                marcado={o.valor === valor}
                radio
                rotulo={o.rotulo}
                contagem={o.total}
                onClick={() => {
                  aoMudar(o.valor);
                  fechar();
                }}
              />
            ))}
            {filtradas.length === 0 && (
              <p className="px-2 py-2 text-sm text-ink-3">Nenhuma opção com esse nome.</p>
            )}
          </div>
        </>
      )}
    </Seletor>
  );
}

// Captação é a lente de EXPLORAÇÃO (filtros específicos + consulta ativa nas
// fontes) — módulo desligável (§29/§40). O menu já esconde o item; o gate
// cobre o acesso direto por URL explicando o porquê (o acompanhamento do
// território continua no Meu painel e em Minhas Propostas).
export default function CaptacaoPage() {
  return (
    <ModuloGate modulo="captacao" titulo="Propostas">
      {/* useSearchParams (lente vinda do Meu painel) exige boundary de Suspense */}
      <Suspense fallback={null}>
        <CaptacaoExploracao />
      </Suspense>
    </ModuloGate>
  );
}

function CaptacaoExploracao() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  // total do recorte no banco — `propostas` é só o que já foi carregado dele
  const [total, setTotal] = useState(0);
  const [porPagina, setPorPagina] = useState(POR_PAGINA_PADRAO);
  const [carregandoMais, setCarregandoMais] = useState(false);
  const [atualizando, setAtualizando] = useState(false);
  const prefCarregada = useRef(false);
  const sentinela = useRef<HTMLDivElement | null>(null);
  const [fontesStatus, setFontesStatus] = useState<FonteStatus[]>([]);
  // quando a última coleta tocou este recorte — a lista vem do banco (o sweep
  // diário é quem alimenta), então a idade do dado precisa estar na tela
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  const [facetas, setFacetas] = useState<Facetas>({});
  const [buscando, setBuscando] = useState(true);
  const [mostrarAvancados, setMostrarAvancados] = useState(false);
  const [favoritos, setFavoritos] = useState<Set<string>>(new Set());
  // proposta_id -> id do monitoramento (para ligar/desligar o alerta pelo card)
  const [alertas, setAlertas] = useState<Map<string, string>>(new Map());
  const [pastas, setPastas] = useState<Pasta[]>([]);
  const [pastaPropostas, setPastaPropostas] = useState<Set<string>>(new Set());
  // território ativo: quais dos municípios do perfil estão em tela agora
  const { selecionados, ativos: municipiosAtivos } = useTerritorio();
  // origem do recurso ativa: de QUAIS fontes o gestor quer ver agora. Como o
  // território, é escolha GLOBAL do trilho — não um filtro desta tela.
  const { selecionadas: origens } = useOrigem();
  const [abas, setAbas] = useState<Aba[]>(abasIniciais);
  const [abaAtiva, setAbaAtiva] = useState<string>(
    () => abasIniciais()[0]?.id ?? "aba-1",
  );
  const [msg, setMsg] = useState<string | null>(null);
  const buscaSeq = useRef(0);

  const acompanhando = abaAtiva === ABA_ACOMPANHAMENTO;
  const aba: Aba = abas.find((a) => a.id === abaAtiva) ??
    abas[0] ?? { id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } };
  const filtros = aba.filtros;
  const [acompanhadas, setAcompanhadas] = useState<Proposta[]>([]);

  // aba ACOMPANHAMENTO: as favoritas completas, direto da API
  const carregarAcompanhadas = useCallback(async () => {
    const { data } = await api.GET("/api/v1/favorites/proposals");
    if (data) setAcompanhadas(data as Proposta[]);
  }, []);
  useEffect(() => {
    if (acompanhando) void carregarAcompanhadas();
  }, [acompanhando, carregarAcompanhadas]);

  useEffect(() => {
    window.localStorage.setItem(ABAS_KEY, JSON.stringify(abas));
  }, [abas]);

  // Os filtros que viajam para a API (os de curadoria ficam no cliente).
  // Vazio vira `undefined` para o parâmetro simplesmente não ir na query.
  const filtrosApi = useCallback(
    () => ({
      // território: o recorte global do painel (barra de filtros), não um filtro
      // desta tela — vazio quando o usuário está vendo todos os municípios.
      municipio: paramMunicipio(selecionados),
      uf: filtros.uf || undefined,
      // origem: idem território — vem do trilho, vazio = todas as fontes
      fonte: paramFonte(origens),
      area: filtros.area || undefined,
      categoria: filtros.categoria || undefined,
      situacao: filtros.situacao || undefined,
      modalidade: filtros.modalidade || undefined,
      orgao: filtros.orgao || undefined,
      natureza_juridica: filtros.naturezaJuridica || undefined,
      natureza_grupo: filtros.naturezaGrupo || undefined,
      qualificacao: filtros.qualificacao || undefined,
      ano: filtros.ano || undefined,
      mes: filtros.mes || undefined,
      q: filtros.q || undefined,
      ordenar: filtros.ordenar || undefined,
      valor_min: filtros.valorMin || undefined,
      valor_max: filtros.valorMax || undefined,
      tipo: filtros.tipo || undefined,
    }),
    [filtros, selecionados, origens],
  );

  /**
   * Carrega uma página do banco. `offset` 0 substitui a lista (troca de filtro);
   * maior que 0 ANEXA (é o "carregar mais"/rolagem infinita).
   *
   * As facetas só vão junto na primeira página: elas contam o recorte inteiro,
   * então não mudam de uma página para a outra.
   */
  const carregarPagina = useCallback(
    async (offset: number) => {
      const seq = ++buscaSeq.current;
      if (offset === 0) setBuscando(true);
      else setCarregandoMais(true);
      const query = { ...filtrosApi(), limite: porPagina, offset };
      const [lista, facs] = await Promise.all([
        api.GET("/api/v1/proposals", { params: { query } as never }),
        offset === 0
          ? api.GET("/api/v1/proposals/facets", {
              params: { query: filtrosApi() } as never,
            })
          : Promise.resolve(null),
      ]);
      if (seq !== buscaSeq.current) return; // resposta antiga — descarta
      if (lista.error) {
        setMsg("Não consegui carregar as propostas. Tente novamente.");
      } else if (lista.data) {
        const pagina = lista.data as {
          itens: Proposta[];
          total: number;
          atualizado_em?: string | null;
        };
        if (offset === 0) setAtualizadoEm(pagina.atualizado_em ?? null);
        setPropostas((prev) =>
          offset === 0 ? (pagina.itens ?? []) : [...prev, ...(pagina.itens ?? [])],
        );
        setTotal(pagina.total ?? 0);
        if (facs?.data) setFacetas(facs.data as Facetas);
        setMsg(null);
      }
      setBuscando(false);
      setCarregandoMais(false);
    },
    [filtrosApi, porPagina],
  );

  // troca de filtro (ou de itens por vez) recomeça da primeira página
  useEffect(() => {
    if (acompanhando) return;
    const t = setTimeout(() => void carregarPagina(0), 400);
    return () => clearTimeout(t);
  }, [carregarPagina, acompanhando]);

  const temMais = propostas.length < total;

  const carregarMais = useCallback(() => {
    if (buscando || carregandoMais || !temMais) return;
    void carregarPagina(propostas.length);
  }, [buscando, carregandoMais, temMais, carregarPagina, propostas.length]);

  // rolagem infinita: a sentinela no fim da lista puxa a próxima página. O
  // botão "Carregar mais" continua ali — quem usa teclado ou tem a rolagem
  // presa em outro contêiner não fica sem saída.
  useEffect(() => {
    const alvo = sentinela.current;
    if (!alvo || acompanhando || !temMais) return;
    const obs = new IntersectionObserver(
      (entradas) => {
        if (entradas[0]?.isIntersecting) carregarMais();
      },
      { rootMargin: "300px" }, // começa a buscar antes de chegar ao fim
    );
    obs.observe(alvo);
    return () => obs.disconnect();
  }, [carregarMais, acompanhando, temMais]);

  // Restaura a preferência de itens por vez uma única vez, no cliente (ler o
  // localStorage no initializer divergiria do HTML do servidor → hidratação).
  useEffect(() => {
    const salvo = lerPorPaginaSalvo();
    if (salvo) setPorPagina(salvo);
    prefCarregada.current = true;
  }, []);

  // Persiste a escolha. O guard evita gravar o padrão por cima da preferência
  // do usuário antes de ela ter sido restaurada.
  useEffect(() => {
    if (!prefCarregada.current) return;
    try {
      window.localStorage.setItem(POR_PAGINA_KEY, String(porPagina));
    } catch {
      /* storage cheio/bloqueado: vale só nesta sessão */
    }
  }, [porPagina]);

  /**
   * "Atualizar fontes" — a coleta ao vivo, agora sob demanda. É a parte cara
   * (API pública + scraping, e um CSV de ~1 GB numa das fontes), por isso saiu
   * do caminho de todo carregamento de tela. Grava no banco e já devolve a
   * primeira página do recorte atualizado.
   */
  const atualizarFontes = useCallback(async () => {
    const seq = ++buscaSeq.current;
    setAtualizando(true);
    setMsg("Consultando as fontes oficiais… pode levar alguns minutos.");
    const f = filtrosApi();
    const { data, error } = await api.POST("/api/v1/proposals/live-search", {
      body: {
        municipios_ibge: f.municipio ?? null,
        uf: f.uf ?? null,
        fonte: f.fonte ?? null,
        area: f.area ?? null,
        categoria: f.categoria ?? null,
        situacao: f.situacao ?? null,
        modalidade: f.modalidade ?? null,
        orgao: f.orgao ?? null,
        natureza_juridica: f.natureza_juridica ?? null,
        qualificacao: f.qualificacao ?? null,
        ano: f.ano ?? null,
        mes: f.mes ?? null,
        q: f.q ?? null,
        ordenar: f.ordenar ?? null,
        valor_min: f.valor_min ?? null,
        valor_max: f.valor_max ?? null,
        tipo: f.tipo ?? null,
        limite: porPagina,
        offset: 0,
        // pedido EXPLÍCITO: ignora o TTL do cache-first e consulta agora. Sem
        // isto o botão herdava as 6h do cache e não consultava nada — a tela
        // dizia "consultando as fontes…" e devolvia o mesmo dado de antes.
        forcar: true,
      } as never,
    });
    setAtualizando(false);
    if (seq !== buscaSeq.current) return; // o usuário mexeu no filtro no meio
    if (error) {
      setMsg("Falha ao atualizar as fontes. Tente de novo em instantes.");
      return;
    }
    const resp = data as {
      propostas: Proposta[];
      total: number;
      fontes: FonteStatus[];
      facetas?: Facetas;
    };
    setPropostas(resp.propostas ?? []);
    setTotal(resp.total ?? 0);
    setFontesStatus(resp.fontes ?? []);
    setFacetas(resp.facetas ?? {});
    setMsg(null);
  }, [filtrosApi, porPagina]);

  const carregarCuradoria = useCallback(async () => {
    const [fav, pas, mon] = await Promise.all([
      api.GET("/api/v1/favorites"),
      api.GET("/api/v1/folders"),
      api.GET("/api/v1/monitors"),
    ]);
    if (fav.data) {
      setFavoritos(
        new Set(
          (fav.data as { proposta_id: string }[]).map((f) => f.proposta_id),
        ),
      );
    }
    if (mon.data) {
      setAlertas(
        new Map(
          (mon.data as { id: string; proposta_id: string }[]).map((m) => [
            m.proposta_id,
            m.id,
          ]),
        ),
      );
    }
    if (pas.data) setPastas(pas.data as Pasta[]);
  }, []);

  useEffect(() => {
    void carregarCuradoria();
  }, [carregarCuradoria]);

  // conteúdo da pasta selecionada (filtro client-side)
  useEffect(() => {
    if (!filtros.pastaId) {
      setPastaPropostas(new Set());
      return;
    }
    void (async () => {
      const { data } = await api.GET("/api/v1/folders/{pasta_id}/proposals", {
        params: { path: { pasta_id: filtros.pastaId } },
      });
      if (data) setPastaPropostas(new Set(data as string[]));
    })();
  }, [filtros.pastaId]);

  // Chegando do Meu painel (`/panel/funding?natureza_grupo=…&ano=…`), a tela
  // abre já na lente E na safra escolhidas no card — o clique não pode trocar o
  // recorte por baixo do usuário. Só na chegada: depois quem manda são os chips.
  const paramsUrl = useSearchParams();
  const lenteUrl = paramsUrl.get("natureza_grupo");
  const lenteValida = LENTES_NATUREZA.some(([v]) => v && v === lenteUrl) ? lenteUrl : null;
  const anoUrl = paramsUrl.get("ano");
  const anoValido = anoUrl && /^\d{4}$/.test(anoUrl) ? anoUrl : null;
  useEffect(() => {
    if (lenteValida) setFiltros({ naturezaGrupo: lenteValida });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lenteValida]);
  useEffect(() => {
    if (anoValido) setFiltros({ ano: anoValido });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anoValido]);

  function setFiltros(patch: Partial<Filtros>) {
    setAbas((prev) =>
      prev.map((a) =>
        a.id === aba.id ? { ...a, filtros: { ...a.filtros, ...patch } } : a,
      ),
    );
  }

  function novaAba() {
    const id = `aba-${Date.now()}`;
    setAbas((prev) => [
      ...prev,
      { id, nome: `Frente ${prev.length + 1}`, filtros: { ...filtros } },
    ]);
    setAbaAtiva(id);
  }

  function fecharAba(id: string) {
    setAbas((prev) => {
      const rest = prev.filter((a) => a.id !== id);
      if (rest.length === 0)
        return [{ id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } }];
      return rest;
    });
    if (abaAtiva === id) setAbaAtiva(abas.find((a) => a.id !== id)?.id ?? "aba-1");
  }

  function renomearAba(id: string) {
    const nome = window.prompt("Nome da aba (projeto, área, região…):");
    if (nome) setAbas((prev) => prev.map((a) => (a.id === id ? { ...a, nome } : a)));
  }

  // A estrela só muda depois que a API confirmou. Marcar antes e ignorar o
  // erro criava a "favorita fantasma": pintada na tela, inexistente no banco —
  // no próximo carregamento ela sumia, como se a persistência falhasse.
  async function alternarFavorito(p: Proposta) {
    const favoritar = !favoritos.has(p.id);
    const { error } = favoritar
      ? await api.POST("/api/v1/favorites", { body: { proposta_id: p.id } })
      : await api.DELETE("/api/v1/favorites/{proposta_id}", {
          params: { path: { proposta_id: p.id } },
        });
    if (error) {
      setMsg(
        favoritar
          ? "Não foi possível favoritar agora — tente novamente."
          : "Não foi possível remover a favorita agora — tente novamente.",
      );
      return;
    }
    setFavoritos((prev) => {
      const s = new Set(prev);
      if (favoritar) s.add(p.id);
      else s.delete(p.id);
      return s;
    });
    if (acompanhando) void carregarAcompanhadas();
  }

  // liga/desliga o alerta (monitoramento) direto do card — canal painel por padrão
  async function alternarAlerta(p: Proposta) {
    const existente = alertas.get(p.id);
    if (existente) {
      await api.DELETE("/api/v1/monitors/{monitoramento_id}", {
        params: { path: { monitoramento_id: existente } },
      });
      setAlertas((prev) => {
        const m = new Map(prev);
        m.delete(p.id);
        return m;
      });
    } else {
      const { data } = await api.POST("/api/v1/monitors", {
        body: { proposta_id: p.id, canais: ["painel"] },
      });
      const novoId = (data as { id?: string } | undefined)?.id;
      if (novoId) setAlertas((prev) => new Map(prev).set(p.id, novoId));
    }
  }

  async function criarPasta() {
    const nome = window.prompt("Nome da nova pasta (projeto, área ou região):");
    if (!nome) return;
    const { data } = await api.POST("/api/v1/folders", { body: { nome } });
    if (data) setPastas((prev) => [...prev, data as Pasta]);
  }

  async function moverParaPasta(propostaId: string, pastaId: string) {
    if (!pastaId) return;
    await api.POST("/api/v1/folders/{pasta_id}/proposals", {
      params: { path: { pasta_id: pastaId } },
      body: { proposta_id: propostaId },
    });
    if (filtros.pastaId === pastaId)
      setPastaPropostas((prev) => new Set(prev).add(propostaId));
    setMsg("Proposta adicionada à pasta.");
  }

  // Filtros de curadoria (favoritas/pasta) são do usuário, não da fonte — ficam
  // no cliente; todo o resto viaja para a API. ATENÇÃO: por serem client-side,
  // eles recortam só o que JÁ foi carregado, não o recorte inteiro do banco.
  // Por isso, com um deles ligado, o contador passa a falar em "carregadas" (o
  // `total` do servidor não os conhece e seria um denominador mentiroso).
  const visiveis = useMemo(() => {
    let lista = acompanhando ? acompanhadas : propostas;
    // no acompanhamento a fonte é a lista de favoritas (não passou pelo filtro
    // da API): o recorte de território vale aqui também.
    if (acompanhando && selecionados.length > 0) {
      const escolhidos = new Set(selecionados);
      lista = lista.filter(
        (p) => p.municipio_ibge && escolhidos.has(p.municipio_ibge),
      );
    }
    if (filtros.soFavoritas) lista = lista.filter((p) => favoritos.has(p.id));
    if (filtros.pastaId) lista = lista.filter((p) => pastaPropostas.has(p.id));
    return lista;
  }, [propostas, acompanhadas, acompanhando, selecionados, filtros.soFavoritas, filtros.pastaId, favoritos, pastaPropostas]);

  const curadoriaAtiva = filtros.soFavoritas || !!filtros.pastaId;

  /** Contador ao lado do rótulo de um chip (vazio quando a opção é "Todas"). */
  function contarFaceta(dim: keyof Facetas, valor: string) {
    if (!valor) return null;
    const total = (facetas[dim] ?? []).find((o) => o.valor === valor)?.total;
    return total ? <span className="ml-1 opacity-60 tabular-nums">{total}</span> : null;
  }

  /** Chips de "filtros ativos" — cada um se remove ao clicar. */
  // quantos filtros avançados estão ativos — mostra badge no toggle mesmo recolhido
  const qtdAvancadosAtivos = [
    filtros.naturezaJuridica,
    filtros.modalidade,
    filtros.orgao,
    filtros.qualificacao,
    filtros.categoria,
    filtros.situacao,
    filtros.uf,
    filtros.ano,
    filtros.mes,
    filtros.area,
    filtros.valorMin,
    filtros.valorMax,
  ].filter(Boolean).length;

  const ativos = useMemo(() => {
    const rotuloDe = (dim: keyof Facetas, valor: string) =>
      (facetas[dim] ?? []).find((o) => o.valor === valor)?.rotulo ?? valor;
    const lista: { chave: string; rotulo: string; limpar: Partial<Filtros> }[] = [];
    if (filtros.q) lista.push({ chave: "q", rotulo: `"${filtros.q}"`, limpar: { q: "" } });
    if (filtros.tipo)
      lista.push({
        chave: "tipo",
        rotulo: filtros.tipo === "disponivel" ? "Disponíveis" : "Cadastradas",
        limpar: { tipo: "" },
      });
    if (filtros.naturezaGrupo)
      lista.push({
        chave: "natureza-grupo",
        rotulo: LENTES_NATUREZA.find(([v]) => v === filtros.naturezaGrupo)?.[1] ?? "",
        limpar: { naturezaGrupo: "" },
      });
    if (filtros.naturezaJuridica)
      lista.push({
        chave: "natureza",
        rotulo: NATUREZAS.find(([v]) => v === filtros.naturezaJuridica)?.[1] ?? "",
        limpar: { naturezaJuridica: "" },
      });
    if (filtros.uf)
      lista.push({ chave: "uf", rotulo: filtros.uf, limpar: { uf: "" } });
    if (filtros.categoria)
      lista.push({
        chave: "categoria",
        rotulo: rotuloDe("categoria", filtros.categoria),
        limpar: { categoria: "" },
      });
    if (filtros.mes)
      lista.push({
        chave: "mes",
        rotulo: rotuloDe("mes", filtros.mes),
        limpar: { mes: "" },
      });
    if (filtros.modalidade)
      lista.push({
        chave: "modalidade",
        rotulo: rotuloDe("modalidade", filtros.modalidade),
        limpar: { modalidade: "" },
      });
    if (filtros.orgao)
      lista.push({ chave: "orgao", rotulo: rotuloDe("orgao", filtros.orgao), limpar: { orgao: "" } });
    if (filtros.qualificacao)
      lista.push({
        chave: "qualificacao",
        rotulo: rotuloDe("qualificacao", filtros.qualificacao),
        limpar: { qualificacao: "" },
      });
    if (filtros.situacao)
      lista.push({
        chave: "situacao",
        rotulo: rotuloDe("situacao", filtros.situacao),
        limpar: { situacao: "" },
      });
    if (filtros.ano)
      lista.push({ chave: "ano", rotulo: `Ano ${filtros.ano}`, limpar: { ano: "" } });
    if (filtros.area)
      lista.push({ chave: "area", rotulo: filtros.area.replace("_", " "), limpar: { area: "" } });
    if (filtros.valorMin)
      lista.push({
        chave: "valorMin",
        rotulo: `≥ ${formatBRL(filtros.valorMin)}`,
        limpar: { valorMin: "" },
      });
    if (filtros.valorMax)
      lista.push({
        chave: "valorMax",
        rotulo: `≤ ${formatBRL(filtros.valorMax)}`,
        limpar: { valorMax: "" },
      });
    if (filtros.soFavoritas)
      lista.push({ chave: "fav", rotulo: "Só favoritas ★", limpar: { soFavoritas: false } });
    if (filtros.pastaId)
      lista.push({
        chave: "pasta",
        rotulo: pastas.find((p) => p.id === filtros.pastaId)?.nome ?? "pasta",
        limpar: { pastaId: "" },
      });
    return lista;
  }, [filtros, facetas, pastas]);

  /** "Baixar relatório": mesmo recorte da tela, em CSV. */
  async function baixarRelatorio() {
    try {
      await baixarCsv(
        "/api/v1/proposals/report.csv",
        {
          // o relatório sai no mesmo recorte da tela, território incluído
          municipio: selecionados,
          uf: filtros.uf,
          // origem: o recorte global do trilho, o mesmo que a tela está vendo
          fonte: origens,
          area: filtros.area,
          categoria: filtros.categoria,
          situacao: filtros.situacao,
          modalidade: filtros.modalidade,
          orgao: filtros.orgao,
          natureza_juridica: filtros.naturezaJuridica,
          qualificacao: filtros.qualificacao,
          ano: filtros.ano,
          mes: filtros.mes,
          q: filtros.q,
          tipo: filtros.tipo,
          valor_min: filtros.valorMin,
          valor_max: filtros.valorMax,
          ordenar: filtros.ordenar,
        },
        "captacao.csv",
      );
    } catch {
      setMsg("Não consegui gerar o relatório agora. Tente novamente.");
    }
  }

  // agregados de EXECUÇÃO (TransfereGov): o que foi disponibilizado × usado
  const execucao = useMemo(() => {
    const com = visiveis.filter((p) => p.execucao);
    if (com.length === 0) return null;
    const soma = (k: "valor_global" | "valor_empenhado" | "valor_liberado" | "valor_pago" | "saldo_conta") =>
      com.reduce((acc, p) => acc + num(p.execucao?.[k]), 0);
    const empenhado = soma("valor_empenhado");
    const pago = soma("valor_pago");
    return {
      transferencias: com.length,
      global: soma("valor_global"),
      empenhado,
      liberado: soma("valor_liberado"),
      pago,
      saldo: soma("saldo_conta"),
      aUtilizar: Math.max(0, empenhado - pago),
    };
  }, [visiveis]);

  const fontesOk = fontesStatus.filter((f) => f.status === "ok").length;
  // linhas que a rodada trouxe (soma do que cada fonte devolveu): é o número que
  // explica uma contagem que mudou — sem ele, "atualizei e agora são outras 5"
  // não tem como ser conferido na tela.
  const linhasColetadas = fontesStatus.reduce((t, f) => t + (f.registros ?? 0), 0);
  // a fonte que falhou sai NOMEADA — "transferegov_disc fora do ar" é slug de
  // integração; o gestor lê "TransfereGov — Discricionárias" (§35)
  const fontesErro = Array.from(
    new Set(
      fontesStatus
        .filter((f) => f.status === "erro")
        .map((f) => rotuloFonte(f.fonte) || f.fonte),
    ),
  );

  return (
    <>
      <PageHeader
        titulo="Propostas"
        descricao={
          <>
            Propostas e oportunidades de{" "}
            {/* condiciona ao que JÁ carregou (não ao recorte salvo no
                localStorage): antes do perfil chegar, cliente e servidor
                precisam renderizar o mesmo texto — senão é erro de hidratação */}
            {selecionados.length > 0 && municipiosAtivos.length > 0 ? (
              <strong className="font-medium text-ink">
                {municipiosAtivos.map(rotuloMunicipio).join(", ")}
              </strong>
            ) : (
              "todo o seu território"
            )}
            .
          </>
        }
        acoes={
          <>
            <Link href="/panel/funding/summary" className="btn btn-ghost btn-sm">
              <IconeAcao nome="resumo" />
              Ver resumo
            </Link>
            {/* A ação MAIS importante da tela (consultar as fontes agora)
                vivia enterrada como ghost pequeno no meio da página; é ação
                primária e mora no cabeçalho, onde toda tela põe a sua. */}
            {!acompanhando && (
              <button
                onClick={() => void atualizarFontes()}
                disabled={atualizando}
                className="btn btn-primary"
                title="Consulta as fontes oficiais agora e grava o que houver de novo. A lista já é atualizada sozinha uma vez por dia."
              >
                {atualizando ? (
                  <>
                    <span className="spinner" aria-hidden />
                    Consultando fontes…
                  </>
                ) : (
                  <>
                    <IconeAcao nome="atualizar" />
                    Atualizar fontes
                  </>
                )}
              </button>
            )}
          </>
        }
      />

      {/* abas — várias frentes de trabalho ao mesmo tempo */}
      <div className="flex flex-wrap items-center gap-1.5">
        {abas.map((a) => (
          <span
            key={a.id}
            /* a aba ativa carrega o fio de gradiente da marca (mesma
               assinatura do card); a inativa reage ao ponteiro em vez de
               ficar parada — era o único controle da tela sem hover. */
            className={`relative inline-flex items-center overflow-hidden rounded-t-lg border border-b-0 border-hairline text-sm transition-colors duration-200 ${
              a.id === abaAtiva
                ? "bg-surface-2 font-medium before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-[var(--fill-accent)]"
                : "text-ink-2 hover:border-ink-2 hover:bg-surface-2/60 hover:text-ink"
            }`}
          >
            <button
              onClick={() => setAbaAtiva(a.id)}
              onDoubleClick={() => renomearAba(a.id)}
              className="px-3 py-1.5"
              title="Duplo clique renomeia"
            >
              {a.nome}
            </button>
            {abas.length > 1 && (
              <button
                onClick={() => fecharAba(a.id)}
                className="pressable pr-2 text-ink-3 hover:text-danger"
                aria-label={`Fechar aba ${a.nome}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
        {/* "Minhas Propostas" agora vive no menu lateral (/panel/my-proposals) */}
        <button onClick={novaAba} className="btn btn-ghost btn-sm" title="Nova aba">
          + aba
        </button>
      </div>

      {/* filtros — cada mudança dispara a busca ao vivo */}
      {!acompanhando && (
      <div className="card flex flex-col gap-3 p-4">
        {/* linha 1 — essenciais (sempre visíveis) */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1">
            <span className="field-label">Buscar</span>
            <input
              value={filtros.q}
              onChange={(e) => setFiltros({ q: e.target.value })}
              // o backend já casa `numero_proposta` — dizer isso aqui é o que
              // transforma o campo em "buscar a proposta pelo número"
              placeholder="nº da proposta, programa ou órgão"
              className="input w-full"
            />
          </label>
          <SelectFaceta
            rotulo="UF"
            valor={filtros.uf}
            opcoes={facetas.uf}
            largura="12rem"
            aoMudar={(v) => setFiltros({ uf: v })}
          />
          {/* A ORIGEM DO RECURSO saiu daqui: é escolha global da barra de
              filtros do painel (`components/FiltrosPainel`), como o território
              (§33). Um filtro em dois lugares dessincroniza — o dropdown local
              recortava só esta tela e o Meu painel continuava mostrando as
              outras fontes. */}
          <SeletorSimples
            rotulo="Ordenar por"
            valor={filtros.ordenar}
            opcoes={ORDENACOES.map(([valor, rotulo]) => ({ valor, rotulo }))}
            vazio={null}
            largura="15rem"
            aoMudar={(v) => setFiltros({ ordenar: v })}
          />
          <button
            onClick={() => void baixarRelatorio()}
            className="btn btn-ghost btn-sm mb-1"
            title="Exporta o recorte atual em CSV"
          >
            ↓ Baixar relatório
          </button>
        </div>

        {/* linha 2 — tipo (esq.) + curadoria e toggle avançados (dir.) */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                ["", "Todas"],
                ["cadastrada", "Cadastradas"],
                ["disponivel", "Disponíveis"],
              ] as const
            ).map(([valor, rotulo]) => (
              <button
                key={rotulo}
                onClick={() => setFiltros({ tipo: valor })}
                className={`rounded-full border px-3 py-1 text-sm ${
                  filtros.tipo === valor
                    ? "border-ink bg-ink text-surface"
                    : "border-hairline text-ink-2 hover:text-ink"
                }`}
              >
                {rotulo}
                {contarFaceta("tipo", valor)}
              </button>
            ))}
            {/* o que separa "cadastrada" de "disponível" — hint da Central */}
            <Hint chave="funding.tipo" />
            {/* lentes de natureza jurídica: quem propõe é o município ou não */}
            <span className="mx-1 h-4 w-px bg-hairline" aria-hidden />
            <span className="field-label mr-1" title="Natureza jurídica do proponente">
              Quem propõe
            </span>
            {LENTES_NATUREZA.map(([valor, rotulo]) => (
              <button
                key={rotulo}
                onClick={() => setFiltros({ naturezaGrupo: valor })}
                title={
                  valor === "entes_municipais"
                    ? "Prefeitura, secretaria, câmara, fundo/autarquia municipal e consórcio intermunicipal"
                    : valor === "outros"
                      ? "Organizações da sociedade civil, entes estaduais/federais e empresas"
                      : "Todas as naturezas jurídicas"
                }
                className={`rounded-full border px-3 py-1 text-sm ${
                  filtros.naturezaGrupo === valor
                    ? "border-ink bg-ink text-surface"
                    : "border-hairline text-ink-2 hover:text-ink"
                }`}
              >
                {rotulo}
                {contarFaceta("natureza_grupo", valor)}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={filtros.soFavoritas}
                onChange={(e) => setFiltros({ soFavoritas: e.target.checked })}
              />
              Só favoritas ★
            </label>
            <select
              value={filtros.pastaId}
              onChange={(e) => setFiltros({ pastaId: e.target.value })}
              className="input w-40"
              title="Filtrar por pasta"
            >
              <option value="">todas as pastas</option>
              {pastas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </select>
            <button onClick={criarPasta} className="btn btn-ghost btn-sm">
              + pasta
            </button>
            <button
              onClick={() => setMostrarAvancados((v) => !v)}
              className="btn btn-ghost btn-sm"
              aria-expanded={mostrarAvancados}
            >
              Filtros avançados
              {qtdAvancadosAtivos > 0 && (
                <span className="ml-1.5 rounded-full bg-ink px-1.5 text-xs text-surface">
                  {qtdAvancadosAtivos}
                </span>
              )}
              <span className="ml-1 text-ink-3">{mostrarAvancados ? "▲" : "▼"}</span>
            </button>
          </div>
        </div>

        {/* filtros avançados — recolhidos por padrão */}
        {mostrarAvancados && (
          <div className="flex flex-col gap-3 border-t border-hairline pt-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="field-label mr-1">Natureza jurídica</span>
              {NATUREZAS.map(([valor, rotulo]) => (
                <button
                  key={rotulo}
                  onClick={() => setFiltros({ naturezaJuridica: valor })}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    filtros.naturezaJuridica === valor
                      ? "border-ink bg-ink text-surface"
                      : "border-hairline text-ink-2 hover:text-ink"
                  }`}
                >
                  {rotulo}
                  {contarFaceta("natureza_juridica", valor)}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <SelectFaceta
                rotulo="Modalidade"
                valor={filtros.modalidade}
                opcoes={facetas.modalidade}
                largura="17rem"
                aoMudar={(v) => setFiltros({ modalidade: v })}
              />
              <SelectFaceta
                rotulo="Órgão"
                valor={filtros.orgao}
                opcoes={facetas.orgao}
                largura="20rem"
                aoMudar={(v) => setFiltros({ orgao: v })}
              />
              <SelectFaceta
                rotulo="Tipo de transferência"
                valor={filtros.qualificacao}
                opcoes={facetas.qualificacao}
                largura="18rem"
                aoMudar={(v) => setFiltros({ qualificacao: v })}
              />
              <SelectFaceta
                rotulo="Categoria"
                valor={filtros.categoria}
                opcoes={facetas.categoria}
                largura="19rem"
                aoMudar={(v) => setFiltros({ categoria: v })}
              />
              <SelectFaceta
                rotulo="Situação"
                valor={filtros.situacao}
                opcoes={facetas.situacao}
                largura="17rem"
                aoMudar={(v) => setFiltros({ situacao: v })}
              />
              <SelectFaceta
                rotulo="Ano"
                valor={filtros.ano}
                opcoes={facetas.ano}
                largura="13rem"
                aoMudar={(v) => setFiltros({ ano: v })}
              />
              {/* o mês acompanha o ano no mesmo referencial: MES_PROP, o mês
                  de CRIAÇÃO da proposta — não é mais o mês do prazo */}
              <SelectFaceta
                rotulo="Mês"
                valor={filtros.mes}
                opcoes={facetas.mes}
                largura="15rem"
                aoMudar={(v) => setFiltros({ mes: v })}
              />
              <SeletorSimples
                rotulo="Área"
                valor={filtros.area}
                opcoes={AREAS.map((a) => ({
                  valor: a,
                  rotulo: a.replace("_", " "),
                }))}
                largura="15rem"
                aoMudar={(v) => setFiltros({ area: v })}
              />
              <label className="flex flex-col gap-1">
                <span className="field-label">Valor mín (R$)</span>
                <input
                  type="number"
                  min={0}
                  value={filtros.valorMin}
                  onChange={(e) => setFiltros({ valorMin: e.target.value })}
                  className="input w-32"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="field-label">Valor máx (R$)</span>
                <input
                  type="number"
                  min={0}
                  value={filtros.valorMax}
                  onChange={(e) => setFiltros({ valorMax: e.target.value })}
                  className="input w-32"
                />
              </label>
            </div>
          </div>
        )}

        {/* filtros ativos — o que está recortando a lista agora */}
        {ativos.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline pt-3">
            <span className="field-label mr-1">Filtros ativos</span>
            {ativos.map((f) => (
              <button
                key={f.chave}
                onClick={() => setFiltros(f.limpar)}
                className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-2 hover:text-ink"
                title="Remover este filtro"
              >
                {f.rotulo}
                <span className="text-ink-3">×</span>
              </button>
            ))}
            <button
              onClick={() => setFiltros(FILTROS_VAZIOS)}
              className="btn btn-ghost btn-sm"
            >
              Limpar tudo
            </button>
          </div>
        )}
      </div>
      )}

      {/* estado honesto da lista: o que já veio, de quanto, e a coleta sob demanda */}
      {!acompanhando && (
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        {buscando ? (
          <span className="label-mono flex items-center gap-2">
            <span className="spinner" aria-hidden />
            Carregando propostas…
          </span>
        ) : curadoriaAtiva ? (
          <span className="label-mono">
            {visiveis.length} de {propostas.length} carregada
            {propostas.length === 1 ? "" : "s"} · {total} no total
          </span>
        ) : (
          <span className="label-mono">
            {propostas.length} de {total} propost{total === 1 ? "a" : "as"}
          </span>
        )}

        <label className="flex items-center gap-1.5">
          <span className="field-label">Por vez</span>
          <select
            value={porPagina}
            onChange={(e) => setPorPagina(Number(e.target.value))}
            className="input h-8 w-20 text-xs"
            aria-label="Propostas por vez"
          >
            {POR_PAGINA_OPCOES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        {/* o botão "Atualizar fontes" subiu para o cabeçalho da página (ação
            primária); aqui fica só o estado honesto da coleta */}

        {/* idade do dado: a lista vem do banco, alimentado pelo sweep diário —
            sem o carimbo, "o número mudou" não tem como ser explicado */}
        {atualizadoEm && !atualizando && (
          <span
            className="label-mono"
            title={`Coleta mais recente deste recorte: ${formatDateTime(atualizadoEm)}`}
          >
            dados de {haQuantoTempo(atualizadoEm)}
          </span>
        )}

        {/* só faz sentido depois de uma atualização — é dela que vem o status */}
        {fontesStatus.length > 0 && !atualizando && (
          <>
            <span className="label-mono">
              {fontesOk} consulta{fontesOk === 1 ? "" : "s"} ok · {linhasColetadas}{" "}
              registro{linhasColetadas === 1 ? "" : "s"}
            </span>
            {fontesErro.length > 0 && (
              <span className="rounded-full bg-warn/10 px-2 py-0.5 font-mono text-[11px] text-warn">
                fora do ar agora: {fontesErro.join(", ")}
              </span>
            )}
          </>
        )}
      </div>
      )}

      {acompanhando && (
        <p className="text-sm text-ink-2">
          Suas propostas favoritadas ★ — toque na estrela para parar de
          acompanhar. Favorite na busca (abas ao lado) para adicionar aqui.
        </p>
      )}

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {/* execução financeira (TransfereGov): quanto foi disponibilizado × usado */}
      {execucao && (
        <section className="stagger grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {/* BRL compacto: em 6 colunas o valor por extenso não cabe e o .card
              corta o que estoura; o valor cheio fica no tooltip (title) */}
          {(
            [
              ["Transferências", String(execucao.transferencias), null, false],
              [
                "Valor global",
                formatBRLCompact(String(execucao.global)),
                formatBRL(String(execucao.global)),
                false,
              ],
              [
                "Empenhado",
                formatBRLCompact(String(execucao.empenhado)),
                formatBRL(String(execucao.empenhado)),
                false,
              ],
              [
                "Empenhado a utilizar",
                formatBRLCompact(String(execucao.aUtilizar)),
                formatBRL(String(execucao.aUtilizar)),
                true,
              ],
              [
                "Pago",
                formatBRLCompact(String(execucao.pago)),
                formatBRL(String(execucao.pago)),
                false,
              ],
              [
                "Saldo em conta",
                formatBRLCompact(String(execucao.saldo)),
                formatBRL(String(execucao.saldo)),
                false,
              ],
            ] as const
          ).map(([rotulo, valor, cheio, destaque]) => (
            <div
              key={rotulo}
              className={`card p-4 ${destaque ? "ring-1 ring-lime" : ""}`}
            >
              {/* min-h de 2 linhas: sem isto o rótulo que quebra ("Empenhado a
                  utilizar") empurra só o seu valor para baixo e a fileira de
                  números deixa de alinhar. */}
              <p className="field-label min-h-[2.2em] leading-tight">{rotulo}</p>
              <p
                className={cx("value-lg mt-1", destaque && "tone-ok")}
                title={cheio ?? undefined}
              >
                {valor}
              </p>
              {destaque && (
                <p className="mt-1 text-[11px] leading-tight text-ink-3">
                  verba disponibilizada ainda não utilizada
                </p>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="overflow-x-auto">
        {visiveis.length === 0 ? (
          <p className="text-ink-3">
            {acompanhando
              ? "Nenhuma favorita ainda — favorite ★ uma proposta na busca para acompanhá-la aqui."
              : buscando
                ? "Carregando propostas…"
                : "Nenhuma proposta com esses filtros. Tente afrouxar o recorte ou use “Atualizar fontes”, no topo da página."}
          </p>
        ) : (
          <div className="card overflow-hidden">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="w-20"></th>
                  <th>Proposta</th>
                  <th>Município</th>
                  {/* a coluna "Prazo" saiu: vinha do fim de vigência, que não é
                      prazo de proposta. O dado segue no detalhe, no card
                      "Prazos", onde é conferível item a item. */}
                  <th>Ano</th>
                  <th className="text-right">Valor global</th>
                  <th className="text-right">Empenhado</th>
                  <th>Situação</th>
                  <th>Pasta</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div className="flex items-center gap-2">
                        <Favorito
                          ativo={favoritos.has(p.id)}
                          onToggle={() => alternarFavorito(p)}
                        />
                        <button
                          onClick={() => alternarAlerta(p)}
                          aria-label="Alerta"
                          title={
                            alertas.has(p.id)
                              ? "Alerta ligado — avisa quando mudar situação/prazo"
                              : "Ligar alerta desta proposta"
                          }
                          className={cx("icon-btn", alertas.has(p.id) && "tone-ok")}
                        >
                          {/* o emoji 🔕 renderizava como pictograma vermelho
                              cortado e lia como estado de ERRO; o glifo abaixo
                              herda currentColor e segue o tema. */}
                          <svg
                            width="15"
                            height="15"
                            viewBox="0 0 24 24"
                            fill={alertas.has(p.id) ? "currentColor" : "none"}
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden
                          >
                            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                            <path d="M13.7 21a2 2 0 0 1-3.4 0" />
                          </svg>
                        </button>
                        {/* espelho em PDF direto da lista — sem abrir a proposta */}
                        <BotaoEspelho propostaId={p.id} formato="icone" />
                      </div>
                    </td>
                    <td>
                      <div className="flex items-start gap-3">
                      {/* Miniatura do registro, como no feed do Meu painel: o
                          alvo marca a proposta DISPONÍVEL (ainda sem cadastro)
                          e o documento, a cadastrada — a distinção que os
                          chips do topo filtram, agora legível na linha. */}
                      <span
                        className="tbl-ico"
                        aria-hidden
                        title={p.tipo === "disponivel" ? "Disponível" : "Cadastrada"}
                      >
                        <IconeNav
                          nome={p.tipo === "disponivel" ? "oportunidades" : "propostas"}
                        />
                      </span>
                      <div className="min-w-0">
                      {/* O nº ENCABEÇA a linha, em pílula: varrer a lista atrás
                          de um número era ler todas as linhas de apoio, onde
                          ele tinha o mesmo peso do órgão e da modalidade.
                          Realçado pelo termo da busca quando ela casa nele.
                          O `id_externo` é plumbing e segue fora daqui — vive no
                          detalhe, em "Dados gerais". */}
                      <NumeroProposta
                        numero={p.numero_proposta}
                        termo={filtros.q}
                        tamanho="sm"
                        className="mb-1"
                      />
                      {/* Título com TETO: sem ele, uma proposta cujo objeto é o
                          projeto inteiro esticava a linha por meia tela e
                          desalinhava a leitura da lista. O gatilho fica FORA do
                          <Link> — botão dentro de âncora é HTML inválido. */}
                      <TextoLimitado
                        texto={humanizarCaixa(p.titulo ?? p.objeto)}
                        limite={110}
                        titulo={municipioPrincipal(p)}
                        rotulo="Objeto da proposta"
                        className="block"
                        vazio={
                          <Link
                            href={`/panel/funding/${p.id}`}
                            className="block font-medium hover:underline"
                          >
                            Proposta sem título na fonte
                          </Link>
                        }
                        envolver={(trecho) => (
                          <Link
                            href={`/panel/funding/${p.id}`}
                            className="font-medium hover:underline"
                          >
                            {trecho}
                          </Link>
                        )}
                      />
                      <p className="mt-0.5 max-w-md text-xs text-ink-3">
                        {[
                          p.data_proposta ? formatDate(p.data_proposta) : null,
                          humanizarCaixa(p.orgao_superior),
                          humanizarCaixa(p.modalidade),
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                      {/* pílulas de categoria — clicar filtra a lista por ela */}
                      {(p.categorias ?? []).length > 0 && (
                        <span className="mt-1 flex flex-wrap gap-1">
                          {p.categorias!.map((c) => (
                            <button
                              key={c.slug}
                              onClick={() => setFiltros({ categoria: c.slug })}
                              title={`Filtrar por ${c.rotulo}`}
                              className={cx(
                                "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                                filtros.categoria === c.slug
                                  ? "border-ink bg-ink text-surface"
                                  : "border-hairline text-ink-3 hover:text-ink",
                              )}
                            >
                              {c.rotulo}
                            </button>
                          ))}
                        </span>
                      )}
                      {p.resumo_ia && (
                        <p className="mt-0.5 line-clamp-2 max-w-md text-xs text-ink-3">
                          {p.resumo_ia}
                        </p>
                      )}
                      </div>
                      </div>
                    </td>
                    <td className="text-ink-2">
                      {/* nome do município; o código só como apoio (seção 23) */}
                      <span className="block">{municipioPrincipal(p)}</span>
                      {municipioSecundario(p) && (
                        <span className="block font-mono text-[11px] text-ink-3">
                          {municipioSecundario(p)}
                        </span>
                      )}
                    </td>
                    {/* Ano da proposta (ANO_PROP na fonte) — a safra, no lugar
                        do prazo. É o mesmo critério do filtro de ano. */}
                    <td className="text-ink-2">
                      {p.ano ? (
                        <span className="num">{p.ano}</span>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                    <td className="num text-right">
                      {formatBRL(p.execucao?.valor_global ?? p.valor_total)}
                    </td>
                    <td className="num text-right">
                      {p.execucao?.valor_empenhado != null ? (
                        <>
                          {formatBRL(p.execucao.valor_empenhado)}
                          {num(p.execucao.valor_empenhado) > num(p.execucao.valor_pago) && (
                            <span
                              className="tone-ok ml-1 align-middle text-[10px]"
                              title="Há verba empenhada ainda não utilizada"
                            >
                              ●
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                    <td>
                      {p.situacao ? (
                        <StatusBadge tone={tomSituacao(p.situacao)}>
                          {humanizarCaixa(p.situacao)}
                        </StatusBadge>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                      <span
                        className={`ml-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${
                          p.tipo === "disponivel"
                            ? "bg-ok/10 text-ok"
                            : "bg-surface-2 text-ink-3"
                        }`}
                      >
                        {p.tipo === "disponivel" ? "disponível" : "cadastrada"}
                      </span>
                    </td>
                    <td>
                      <select
                        defaultValue=""
                        onChange={(e) => {
                          void moverParaPasta(p.id, e.target.value);
                          e.target.value = "";
                        }}
                        className="input h-8 w-28 text-xs"
                        aria-label="Adicionar à pasta"
                      >
                        <option value="">+ pasta</option>
                        {pastas.map((pa) => (
                          <option key={pa.id} value={pa.id}>
                            {pa.nome}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Fim da lista: a sentinela dispara a próxima página ao entrar na tela
            e o botão faz o mesmo por clique. */}
        {!acompanhando && propostas.length > 0 && (
          <div ref={sentinela} className="flex flex-col items-center gap-2 py-6">
            {temMais ? (
              <>
                <button
                  onClick={carregarMais}
                  disabled={carregandoMais}
                  className="btn btn-ghost btn-sm disabled:opacity-50"
                >
                  {carregandoMais ? (
                    <>
                      <span className="spinner" aria-hidden />
                      Carregando…
                    </>
                  ) : (
                    `Carregar mais (${total - propostas.length} restantes)`
                  )}
                </button>
                <span className="label-mono text-ink-3">
                  {propostas.length} de {total}
                </span>
              </>
            ) : (
              <span className="label-mono text-ink-3">
                Fim da lista — {total} propost{total === 1 ? "a" : "as"}
              </span>
            )}
          </div>
        )}
      </section>
    </>
  );
}
