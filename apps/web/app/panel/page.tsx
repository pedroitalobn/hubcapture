"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { Favorito } from "@/components/Favorito";
import { NumeroProposta } from "@/components/NumeroProposta";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api/client";
import {
  formatBRL,
  formatBRLCompact,
  humanizarCaixa,
  municipioPrincipal,
  recortarTexto,
} from "@/lib/format";
import { rotuloFonte } from "@/lib/fontes";
import { paramFonte, useOrigem } from "@/lib/origem";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

// ── Panorama financeiro do território (números + gráfico) ───────────────────
// Reusa /proposals/summary (mesma fonte da página de resumo da Captação) para
// dar cards e um gráfico por ano direto no Meu painel. A safra vem do filtro da
// PÁGINA (prop `ano`), não de um seletor próprio: dois filtros de ano na mesma
// tela mostravam recortes diferentes lado a lado — o gráfico obedecia a um, os
// cards e o feed continuavam no outro.
//
// O panorama deixou de ser uma seção própria: com poucas dimensões ativas, o
// card do nº de propostas ficava sozinho numa grade de 4 colunas e a linha
// inteira era vão. O gráfico aprovado × desembolsado entra NA MESMA grade,
// fechando a linha ao lado do número, e os KPIs financeiros viram uma faixa
// de cards logo abaixo, com as cores cheias da marca (tinta, lime, aqua e o
// gradiente) — contraste de verdade sobre o canvas claro, em vez de mais
// quatro cards brancos.
interface ResumoPainelData {
  cards: {
    valor_conveniado: string;
    valor_desembolsado: string;
    valor_empenhado: string;
    valor_pago: string;
    valor_publicado: string;
    propostas_publicadas: number;
    valor_a_utilizar: string;
    transferencias: number;
    convenios_em_execucao: number;
    oportunidades_abertas: number;
  };
  por_ano: { ano: string; aprovado: string; desembolsado: string }[];
  // abertura mês a mês — a API só a manda quando o recorte é de UMA safra
  por_mes?: { mes: string; rotulo: string; aprovado: string; desembolsado: string }[];
}

function numBR(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** Busca o resumo financeiro do recorte (safras + território). `habilitado`
 *  segura a consulta enquanto o perfil não confirmou território — sem ele, a
 *  conta recém-criada pagaria um summary vazio a cada carga. */
function useResumoFinanceiro(anos: string[], habilitado: boolean) {
  const { selecionados } = useTerritorio();
  const { selecionadas: origens } = useOrigem();
  const [resumo, setResumo] = useState<ResumoPainelData | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    if (!habilitado) return;
    setCarregando(true);
    void api
      .GET("/api/v1/proposals/summary", {
        params: {
          query: {
            ano: anos.length ? anos : undefined,
            municipio: paramMunicipio(selecionados),
            fonte: paramFonte(origens),
          },
        } as never,
      })
      .then(({ data }) => {
        // `if (data)` deixava passar qualquer coisa truthy (um [] inclusive),
        // e aí `resumo.por_ano.map` derrubava a tela inicial INTEIRA — não só
        // este bloco, porque não há error boundary aqui. O painel é a porta de
        // entrada do app; ele precisa degradar, não sumir.
        const ok =
          data &&
          Array.isArray((data as ResumoPainelData).por_ano) &&
          (data as ResumoPainelData).cards;
        if (ok) setResumo(data as ResumoPainelData);
        setCarregando(false);
      });
  }, [anos, selecionados, origens, habilitado]);

  return { resumo, carregando };
}

// Quantas colunas (grade xl de 4) o gráfico ocupa ao lado dos cards de
// dimensão: com 1–2 dimensões ele fecha a linha; com mais, desce inteiro
// para a linha seguinte. Mapa de literais — Tailwind não enxerga classe
// montada por template.
const SPAN_GRAFICO: Record<number, string> = {
  1: "xl:col-span-3",
  2: "xl:col-span-2",
};

/** Gráfico aprovado × desembolsado, morando na MESMA grade das dimensões —
 *  é ele que preenche o vão ao lado do nº de propostas.
 *
 *  Com UMA safra selecionada o gráfico troca de escala: em vez de repetir a
 *  barra única do ano, abre o mesmo par mês a mês daquele ano (`por_mes` da
 *  API). As barras transicionam a altura em CSS — trocar de safra morfa o
 *  desenho em vez de piscar um novo. */
function GraficoAprovadoDesembolsado({
  resumo,
  anos,
  className = "",
}: {
  resumo: ResumoPainelData;
  anos: string[];
  className?: string;
}) {
  const porMes = anos.length === 1 ? (resumo.por_mes ?? []) : [];
  const mensal = porMes.length > 0;
  // no modo mensal a série é a dos meses; no anual, a dos anos
  const serie = mensal
    ? porMes.map((m) => ({
        chave: m.mes,
        rotulo: m.rotulo.slice(0, 3).toLowerCase(),
        aprovado: m.aprovado,
        desembolsado: m.desembolsado,
      }))
    : (resumo.por_ano ?? []).map((a) => ({
        chave: a.ano,
        rotulo: a.ano,
        aprovado: a.aprovado,
        desembolsado: a.desembolsado,
      }));
  const teto = Math.max(
    1,
    ...serie.flatMap((s) => [numBR(s.aprovado), numBR(s.desembolsado)]),
  );
  const recorte =
    anos.length === 0
      ? "todas as safras"
      : anos.length === 1
        ? `safra ${anos[0]}${mensal ? " · mês a mês" : ""}`
        : `safras ${[...anos].sort().join(" + ")}`;
  return (
    <div className={`card flex flex-col justify-between p-4 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="label-mono">
          {mensal
            ? "Aprovado × desembolsado por mês"
            : "Aprovado × desembolsado por ano"}
        </h3>
        <span className="label-mono">{recorte}</span>
      </div>
      {/* key = escala: trocar ano→mês remonta com fade; ano→ano e mês→mês
          mantém os elementos e a transition morfa as alturas */}
      <div
        key={mensal ? "mensal" : "anual"}
        className="anim-fade-in mt-3 flex items-end gap-2 overflow-x-auto"
      >
        {serie.map((s) => (
          <div
            key={s.chave}
            className={`flex flex-col items-center gap-1 ${
              mensal ? "min-w-[26px]" : "min-w-[42px]"
            }`}
          >
            <div className="flex h-16 items-end gap-0.5">
              <div
                title={`Aprovado: ${formatBRL(s.aprovado)}`}
                className="w-3 rounded-t bg-ink/70 transition-[height] duration-500 ease-out"
                style={{ height: `${(numBR(s.aprovado) / teto) * 100}%` }}
              />
              <div
                title={`Desembolsado: ${formatBRL(s.desembolsado)}`}
                className="w-3 rounded-t bg-lime transition-[height] duration-500 ease-out"
                style={{ height: `${(numBR(s.desembolsado) / teto) * 100}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-ink-3">{s.rotulo}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 font-mono text-[11px] text-ink-3">
        <span className="mr-3">▊ aprovado</span>
        <span className="text-lime">▊ desembolsado</span>
      </p>
    </div>
  );
}

/** Faixa de KPIs financeiros — cores cheias da marca, uma por card, para o
 *  bloco contrastar com o canvas e com os cards brancos do restante. */
function CardsFinanceiros({ resumo }: { resumo: ResumoPainelData }) {
  const cards = resumo.cards;
  return (
    <section className="stagger grid grid-cols-2 gap-4 md:grid-cols-4">
      {/* BRL compacto no KPI (R$ 5,63 mi): por extenso não cabe no card de
          2 colunas do celular e o .card corta o que estoura. O valor cheio
          fica no tooltip (title). */}
      <StatCard
        tone="ink"
        label="Total geral"
        value={formatBRLCompact(cards.valor_conveniado)}
        title={formatBRL(cards.valor_conveniado)}
        context={`${cards.transferencias} transferências`}
      />
      <StatCard
        tone="lime"
        label="Empenhado"
        value={formatBRLCompact(cards.valor_empenhado)}
        title={formatBRL(cards.valor_empenhado)}
        context="reservado pelo concedente"
      />
      {/* "Publicado" vem da fonte ora como valor, ora como estado. Com
          valor, mostra o valor; sem ele, a contagem de publicadas — R$ 0,00
          leria como "nada publicado", que é outra coisa. */}
      <StatCard
        tone="aqua"
        label="Publicado"
        value={
          numBR(cards.valor_publicado) > 0
            ? formatBRLCompact(cards.valor_publicado)
            : String(cards.propostas_publicadas)
        }
        title={
          numBR(cards.valor_publicado) > 0
            ? formatBRL(cards.valor_publicado)
            : undefined
        }
        context={
          numBR(cards.valor_publicado) > 0
            ? "publicado pela fonte"
            : "propostas publicadas"
        }
      />
      <StatCard
        tone="grad"
        label="Pago"
        value={formatBRLCompact(cards.valor_pago)}
        title={formatBRL(cards.valor_pago)}
        context="efetivamente pago"
      />
    </section>
  );
}

interface Quebra {
  chave: string;
  rotulo: string;
  total: number;
  href: string;
}
interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  // null = módulo de exploração desligado — o card informa, sem navegar (§40)
  href?: string | null;
  // recortes dentro da dimensão, já com link filtrado (ex.: natureza jurídica)
  quebras?: Quebra[];
  // false = dimensão sem safra anual (conformidade/obras são estado atual)
  recorte_ano?: boolean;
}
interface Municipio {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
}
interface VisaoGeral {
  papel?: string | null;
  municipios: Municipio[];
  areas: string[];
  dimensoes: Dimensao[];
}
interface Novidade {
  tipo: string;
  titulo: string;
  descricao?: string | null;
  valor?: number | string | null;
  data?: string | null;
  // safra do item (ano da proposta / do repasse) — o mesmo critério do filtro
  ano?: string | null;
  fonte: string;
  /** nome da fonte como o gestor a chama (a API resolve; o slug nunca sai) */
  fonte_rotulo?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  href: string;
  proposta_id?: string | null;
  numero_proposta?: string | null;
}
interface SyncRunStatus {
  fonte?: string | null;
  status?: string | null;
  registros?: number | null;
  finalizado_em?: string | null;
}
interface AnoDisponivel {
  ano: string;
  total: number;
}
interface Novidades {
  itens: Novidade[];
  sync_runs: SyncRunStatus[];
  // safras COM novidade no território, do mais recente ao mais antigo. Vem
  // sempre do território inteiro — escolher um ano não pode apagar as outras
  // opções do próprio filtro.
  anos?: AnoDisponivel[];
}
interface Noticia {
  titulo: string;
  url: string;
  data?: string | null;
  resumo?: string | null;
}
interface Alerta {
  id: string;
  lido: boolean;
}

/** Descrição do item, salvo quando ela só repete o rótulo da fonte. */
function descricaoUtil(n: Novidade): string | null {
  const descricao = (n.descricao ?? "").trim();
  if (!descricao) return null;
  const fonte = (n.fonte_rotulo || rotuloFonte(n.fonte)).toLowerCase();
  return fonte.includes(descricao.toLowerCase()) ? null : descricao;
}

function brl(v: number | string | null | undefined): string | null {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (n == null || Number.isNaN(n)) return null;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function dataBr(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

// ── Filtro de ano do painel ─────────────────────────────────────────────────
// UM filtro para a página inteira: cards das dimensões, panorama financeiro
// (números + gráfico) e feed de novidades pedem a MESMA safra à API. Antes o
// gráfico tinha um seletor próprio e o feed, pills separadas — filtrar o ano
// ajustava o gráfico e deixava os cards em outro recorte.
//
// As opções vêm do território inteiro (`anos` do feed), então escolher 2024
// não apaga as outras safras do seletor; o recorte é do SERVIDOR, então uma
// safra antiga traz os itens daquele ano em vez de garimpar o que sobrou na
// janela. A escolha persiste entre visitas.
//
// A forma é uma LINHA DE CHIPS à esquerda, sob o título — não um <select>
// no canto direito do cabeçalho: escondido lá, o filtro passava despercebido
// e o ano escolhido não se via sem abrir o dropdown. O chip ativo usa o
// acento da marca (`.chip-active`), então a safra em vigor está sempre à
// vista; as mais antigas colapsam num dropdown para o território com muitas
// safras não virar uma parede de chips.
const ANO_KEY = "hub_painel_ano";
const ANOS_EM_CHIP = 6;
// Janela do feed: quantos itens da safra escolhida (ou das mais recentes,
// quando "todos os anos") cabem na lista.
const FEED_LIMITE = 60;

/** Preferência salva do filtro de safra ([] = todos os anos). O valor é uma
 *  lista separada por vírgula; o formato antigo (um ano só) continua lendo. */
function lerAnosSalvos(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const salvo = window.localStorage.getItem(ANO_KEY) ?? "";
    return salvo.split(",").filter((a) => /^\d{4}$/.test(a));
  } catch {
    return []; // preferência corrompida/indisponível → todos os anos
  }
}

function MeuPainel() {
  const searchParams = useSearchParams();
  const sincronizando = searchParams.get("sync") === "1";
  // recorte de município escolhido no trilho lateral (vazio = todo o território)
  const { selecionados } = useTerritorio();
  // recorte de ORIGEM DO RECURSO, do mesmo trilho (vazio = todas as fontes)
  const { selecionadas: origens } = useOrigem();

  const [data, setData] = useState<VisaoGeral | null>(null);
  const [novidades, setNovidades] = useState<Novidades | null>(null);
  const [noticias, setNoticias] = useState<Noticia[]>([]);
  const [naoLidos, setNaoLidos] = useState(0);
  const [favoritas, setFavoritas] = useState<Set<string>>(new Set());
  const [favErro, setFavErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const tentativas = useRef(0);
  // [] = todos os anos; a seleção é um CONJUNTO de safras (multi-seleção nos
  // chips). Ler o localStorage já no initializer divergiria do HTML do
  // servidor, que não tem acesso a ele — erro de hidratação; a restauração
  // acontece no efeito abaixo.
  const [anos, setAnos] = useState<string[]>([]);
  const prefCarregada = useRef(false);
  // Panorama financeiro (gráfico + faixa de KPIs) — só consulta depois que o
  // perfil confirmou território.
  const { resumo, carregando: carregandoResumo } = useResumoFinanceiro(
    anos,
    (data?.municipios.length ?? 0) > 0,
  );
  /** Liga/desliga uma safra no conjunto (clique no chip). */
  const alternarAno = useCallback((safra: string) => {
    setAnos((prev) =>
      prev.includes(safra) ? prev.filter((a) => a !== safra) : [...prev, safra],
    );
  }, []);

  // O recorte de município, a ORIGEM DO RECURSO e a safra entram em TODA
  // consulta do painel: trocar o território ou a origem no trilho lateral, ou
  // o ano no filtro, refaz visão geral, panorama e feed — todos no mesmo
  // recorte. Filtro global que só vale em uma das telas lê como quebrado.
  const carregar = useCallback(async () => {
    const municipio = paramMunicipio(selecionados);
    const query = {
      municipio,
      fonte: paramFonte(origens),
      ano: anos.length ? anos : undefined,
    };
    const [{ data: vg }, { data: nov }] = await Promise.all([
      api.GET("/api/v1/profile/overview", { params: { query } }),
      api.GET("/api/v1/profile/feed", {
        params: { query: { ...query, limite: FEED_LIMITE } },
      }),
    ]);
    if (vg) setData(vg as VisaoGeral);
    if (nov) setNovidades(nov as Novidades);
    setLoading(false);
    // `?.itens.length` protegia contra `nov` ausente mas NÃO contra `itens`
    // ausente — um nível a menos de defesa do que o próprio `?.` pretendia.
    // Sem o segundo `?.`, um feed sem `itens` derruba a tela inicial inteira.
    return (nov as Novidades | undefined)?.itens?.length ?? 0;
  }, [selecionados, origens, anos]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    // painel informativo (notícias oficiais) + alertas não lidos — best-effort
    void (async () => {
      const [not, al] = await Promise.all([
        api.GET("/api/v1/news", { params: { query: { limite: 5 } } }),
        api.GET("/api/v1/alerts", {
          params: {
            query: { nao_lidos: true, municipio: paramMunicipio(selecionados) },
          },
        }),
      ]);
      if (not.data) setNoticias(not.data as Noticia[]);
      if (al.data) setNaoLidos((al.data as Alerta[]).length);
    })();
  }, [selecionados]);

  useEffect(() => {
    // Favoritas do usuário — alimenta a ★ do feed. O painel NÃO faz consulta
    // ativa nas fontes (live-search): isso é exploração do módulo Captação
    // (§40); aqui é leitura do cache do território, sempre disponível.
    void api.GET("/api/v1/favorites").then(({ data }) => {
      if (data)
        setFavoritas(
          new Set(
            (data as { proposta_id: string }[]).map((f) => f.proposta_id),
          ),
        );
    });
  }, []);

  // Restaura a preferência salva uma única vez, no cliente.
  useEffect(() => {
    const salvos = lerAnosSalvos();
    if (salvos.length) setAnos(salvos);
    prefCarregada.current = true;
  }, []);

  // Persiste a escolha. O guard evita o efeito rodar ANTES da restauração e
  // gravar o padrão por cima do que o usuário já tinha escolhido.
  useEffect(() => {
    if (!prefCarregada.current) return;
    try {
      window.localStorage.setItem(ANO_KEY, anos.join(","));
    } catch {
      /* storage cheio/bloqueado: o filtro segue valendo nesta sessão */
    }
  }, [anos]);

  // A estrela só muda depois que a API confirmou — marcar antes e ignorar o
  // erro criava a "favorita fantasma" que sumia no próximo carregamento.
  async function alternarFavorita(id: string) {
    const favoritar = !favoritas.has(id);
    const { error } = favoritar
      ? await api.POST("/api/v1/favorites", { body: { proposta_id: id } })
      : await api.DELETE("/api/v1/favorites/{proposta_id}", {
          params: { path: { proposta_id: id } },
        });
    if (error) {
      setFavErro(
        favoritar
          ? "Não foi possível favoritar agora — tente novamente."
          : "Não foi possível remover a favorita agora — tente novamente.",
      );
      return;
    }
    setFavErro(null);
    setFavoritas((prev) => {
      const s = new Set(prev);
      if (favoritar) s.add(id);
      else s.delete(id);
      return s;
    });
  }

  // Recém-saído do onboarding: o 1º sync real roda em background na API —
  // re-consulta o feed a cada 8s (até ~2min) enquanto os dados chegam.
  useEffect(() => {
    if (!sincronizando) return;
    const timer = setInterval(async () => {
      tentativas.current += 1;
      const n = await carregar();
      if (n > 0 || tentativas.current >= 15) clearInterval(timer);
    }, 8000);
    return () => clearInterval(timer);
  }, [sincronizando, carregar]);

  const semTerritorio = !loading && (data?.municipios.length ?? 0) === 0;
  const itens = novidades?.itens ?? [];
  // Safras oferecidas pelo filtro: o que EXISTE no território (vem da API, já
  // do mais recente ao mais antigo e independente do ano escolhido).
  const anosDisponiveis = useMemo(
    () =>
      [...(novidades?.anos ?? [])].sort((a, b) => b.ano.localeCompare(a.ano)),
    [novidades],
  );
  // Safra salva que não existe mais no território (município trocado, cache
  // zerado) prenderia o painel num recorte vazio — sai do conjunto; sem
  // nenhuma sobrando, volta para "todos os anos".
  useEffect(() => {
    if (!anos.length || !novidades) return;
    const existentes = new Set((novidades.anos ?? []).map((a) => a.ano));
    const validos = anos.filter((a) => existentes.has(a));
    if (validos.length !== anos.length) setAnos(validos);
  }, [anos, novidades]);
  const dimensoes = data?.dimensoes ?? [];
  // Dimensões que não têm safra (conformidade/obras): o painel avisa em vez de
  // deixar o usuário achar que o filtro falhou nesses cards.
  const semSafra = anos.length
    ? dimensoes.filter((d) => d.recorte_ano === false).map((d) => d.titulo)
    : [];
  // Safras em chip (as mais recentes) × safras antigas (dropdown compacto).
  const anosChip = anosDisponiveis.slice(0, ANOS_EM_CHIP);
  const anosAntigos = anosDisponiveis.slice(ANOS_EM_CHIP);
  const antigosAtivos = anosAntigos.filter((a) => anos.includes(a.ano)).length;
  const falhas = (novidades?.sync_runs ?? []).filter((r) => r.status === "erro");
  const aguardandoDados =
    sincronizando && itens.length === 0 && tentativas.current < 15;

  return (
    <>
      <header>
        <h1 className="page-title">Meu painel</h1>
        <p className="mt-1 text-sm text-ink-2">
          Tudo do seu território, por etapa do ciclo do recurso público.
        </p>
        {/* Filtro de safra da PÁGINA: cards, panorama e novidades no mesmo
            recorte. Chips à esquerda, sob o título — MULTI-SELEÇÃO: cada
            clique liga/desliga a safra no conjunto (comparar 2024+2025 é um
            recorte legítimo); "Todos os anos" limpa. Só aparece quando o
            território tem alguma safra — filtro que não muda nada parece
            quebrado. */}
        {!semTerritorio && anosDisponiveis.length > 0 && (
          <nav
            aria-label="Filtrar o painel por safra (ano) — selecione uma ou várias"
            className="mt-4 flex flex-wrap items-center gap-2"
          >
            <span className="label-mono">Safra</span>
            {anosDisponiveis.length === 1 ? (
              <span
                className="chip chip-active cursor-default"
                title="O território tem uma única safra — não há o que recortar"
              >
                {anosDisponiveis[0]?.ano}
                <span className="tabular-nums opacity-60">
                  {anosDisponiveis[0]?.total}
                </span>
              </span>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => setAnos([])}
                  className={`chip ${anos.length === 0 ? "chip-active" : ""}`}
                  aria-pressed={anos.length === 0}
                  title="Painel inteiro, sem recorte de safra"
                >
                  Todos os anos
                </button>
                {anosChip.map((a) => (
                  <button
                    key={a.ano}
                    type="button"
                    onClick={() => alternarAno(a.ano)}
                    className={`chip ${anos.includes(a.ano) ? "chip-active" : ""}`}
                    aria-pressed={anos.includes(a.ano)}
                    title={`Liga/desliga a safra ${a.ano} no recorte (dá para somar várias)`}
                  >
                    {a.ano}
                    <span className="tabular-nums opacity-60">{a.total}</span>
                  </button>
                ))}
                {anosAntigos.length > 0 && (
                  // o select soma/remove a safra antiga escolhida; o valor
                  // volta sempre a "anteriores…" porque a seleção vive nos
                  // chips (o ✓ das opções mostra o que já está ligado)
                  <select
                    value=""
                    onChange={(e) => e.target.value && alternarAno(e.target.value)}
                    className={`chip ${antigosAtivos ? "chip-active" : ""}`}
                    title="Safras mais antigas do território — escolher soma ao recorte"
                  >
                    <option value="">
                      anteriores…{antigosAtivos ? ` (${antigosAtivos})` : ""}
                    </option>
                    {anosAntigos.map((a) => (
                      <option key={a.ano} value={a.ano}>
                        {anos.includes(a.ano) ? "✓ " : ""}
                        {a.ano} ({a.total})
                      </option>
                    ))}
                  </select>
                )}
              </>
            )}
          </nav>
        )}
      </header>

      {naoLidos > 0 && (
        <Link
          href="/panel/alerts"
          className="card card-hover flex items-center justify-between p-4 text-sm"
        >
          <span>
            🔔 Você tem <strong>{naoLidos}</strong>{" "}
            {naoLidos === 1 ? "alerta não lido" : "alertas não lidos"} — novas
            propostas, prazos e oportunidades.
          </span>
          <span className="btn btn-ghost btn-sm">Ver alertas →</span>
        </Link>
      )}

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <div className="card p-8 text-sm">
          <p className="mb-2 text-base tracking-tight">
            Você ainda não acompanha nenhum município.
          </p>
          <p className="mb-5 max-w-md leading-relaxed text-ink-2">
            O Hub Capture se organiza a partir do seu perfil — converse com o
            Copiloto para escolher municípios, áreas e fontes.
          </p>
          <Link href="/onboarding" className="btn btn-primary">
            Configurar meu perfil
          </Link>
        </div>
      ) : (
        <>
          <section className="stagger grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {dimensoes.map((d) => {
              // sem href = módulo de exploração desligado: o número do
              // território continua no painel, só não há para onde navegar
              const conteudo = (
                <>
                  <div className="flex items-start justify-between">
                    <h2 className="tracking-tight">{d.titulo}</h2>
                    {d.href && (
                      <span className="flex h-9 w-9 translate-y-1 items-center justify-center rounded-lg bg-lime text-abyss opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
                        →
                      </span>
                    )}
                  </div>
                  <div>
                    {/* key = valor: trocar safra/território remonta o número e
                        o anim-swap suaviza a troca (nada de corte seco) */}
                    <div
                      key={d.total}
                      className={`anim-swap text-[34px] font-medium leading-none tracking-[-0.03em] tabular-nums ${
                        d.total > 0 ? "text-gradient" : ""
                      }`}
                    >
                      {d.total}
                    </div>
                    {d.destaque && (
                      <p className="mt-2 text-sm text-ink-2">{d.destaque}</p>
                    )}
                  </div>
                </>
              );
              // recortes da dimensão (ex.: natureza jurídica na captação):
              // ficam FORA do <Link> do card — âncora dentro de âncora não vale
              const quebras = (d.quebras ?? []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {(d.quebras ?? []).map((q) => (
                    <Link
                      key={q.chave}
                      href={q.href}
                      className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1 text-xs text-ink-2 transition hover:text-ink"
                    >
                      {q.rotulo}
                      <span className="tabular-nums opacity-60">{q.total}</span>
                    </Link>
                  ))}
                </div>
              );
              return (
                <div key={d.chave} className="flex flex-col gap-2">
                  {d.href ? (
                    <Link
                      href={d.href}
                      className="card card-hover group flex flex-1 flex-col justify-between gap-3 p-5 min-h-28"
                    >
                      {conteudo}
                    </Link>
                  ) : (
                    <div className="card flex flex-1 flex-col justify-between gap-3 p-5 min-h-28">
                      {conteudo}
                    </div>
                  )}
                  {quebras}
                </div>
              );
            })}
            {/* O gráfico fecha a linha ao lado do nº de propostas — é o que
                ocupa o vão da grade quando poucas dimensões estão ativas. */}
            {resumo && (resumo.por_ano?.length ?? 0) > 0 && (
              <GraficoAprovadoDesembolsado
                resumo={resumo}
                anos={anos}
                className={`sm:col-span-2 ${
                  SPAN_GRAFICO[dimensoes.length] ?? "xl:col-span-4"
                }`}
              />
            )}
          </section>

          {carregandoResumo && !resumo ? (
            <SkeletonCards />
          ) : resumo ? (
            <CardsFinanceiros resumo={resumo} />
          ) : null}

          {semSafra.length > 0 && (
            <p className="text-[12px] text-ink-3">
              {semSafra.join(" e ")}{" "}
              {semSafra.length === 1 ? "mostra" : "mostram"} o estado atual do
              município — {semSafra.length === 1 ? "não tem" : "não têm"} recorte
              por ano.
            </p>
          )}

          <section className="anim-fade-up flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="tracking-tight">
                Propostas{" "}
                <span className="text-ink-3">(filtro conforme o ano)</span>
              </h2>
              {aguardandoDados && (
                <span className="label-mono animate-pulse">
                  Sincronizando fontes…
                </span>
              )}
            </div>

            {favErro && (
              <p role="status" className="text-sm tone-danger">
                {favErro}
              </p>
            )}

            {itens.length === 0 ? (
              <div className="card p-6 text-sm text-ink-2">
                {aguardandoDados ? (
                  <p>
                    Estamos consultando as fontes oficiais do seu perfil agora —
                    as primeiras verbas e propostas aparecem aqui em instantes.
                  </p>
                ) : falhas.length > 0 ? (
                  <p>
                    Ainda sem dados no cache: {falhas.length}{" "}
                    {falhas.length === 1 ? "fonte falhou" : "fontes falharam"} na
                    última coleta (
                    {falhas
                      .map((f) => rotuloFonte(f.fonte) || f.fonte)
                      .join(", ")}
                    ). Novas tentativas rodam no próximo ciclo; você também pode
                    disparar uma busca nas páginas de cada dimensão.
                  </p>
                ) : anos.length ? (
                  <p>
                    Nenhuma novidade de {anos.join(", ")} no território —{" "}
                    <button
                      type="button"
                      onClick={() => setAnos([])}
                      className="underline underline-offset-2"
                    >
                      ver todos os anos
                    </button>
                    .
                  </p>
                ) : (
                  <p>
                    Nenhuma novidade ainda — os dados chegam após a primeira
                    coleta das fontes do seu perfil.
                  </p>
                )}
              </div>
            ) : (
              // key = recorte: trocar safra/território re-encena o fade da
              // lista em vez de trocar as linhas secamente no lugar
              <ol
                key={`${anos.join("+")}|${selecionados.join("+")}`}
                className="card stagger divide-y divide-hairline p-0"
              >
                {itens.map((n, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 pr-3 row-interactive"
                  >
                    {/* Favoritar e exportar direto do painel — só propostas de
                        captação (repasse não tem espelho nem favorita). A
                        COLUNA, porém, existe em toda linha: sem ela as linhas
                        de repasse começavam coladas na borda e a lista tinha
                        duas margens esquerdas, com o texto do FNS desalinhado
                        do das propostas. */}
                    <span className="flex shrink-0 items-center gap-2 pl-4">
                      {n.proposta_id ? (
                        <>
                          <Favorito
                            ativo={favoritas.has(n.proposta_id)}
                            onToggle={() => alternarFavorita(n.proposta_id!)}
                            rotuloOff="Favoritar esta proposta"
                          />
                          <BotaoEspelho propostaId={n.proposta_id} formato="icone" />
                        </>
                      ) : (
                        // o vão dos dois botões: 2rem cada (`.fav`/`.icon-btn`)
                        // mais o gap-2 entre eles
                        <span className="h-8 w-[4.5rem]" aria-hidden />
                      )}
                    </span>
                    <Link
                      href={n.href}
                      className="flex flex-1 flex-col gap-1 px-2 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        {/* O nº abre o item: é por ele que o gestor localiza a
                            proposta no meio do feed (§35). Sem número — caso
                            dos repasses — a linha começa direto no título. */}
                        <p className="flex min-w-0 items-center gap-2">
                          <NumeroProposta
                            numero={n.numero_proposta}
                            tamanho="sm"
                            copiavel={false}
                          />
                          {/* Teto de 80 caracteres: o título do item é o
                              `objeto` da fonte e vem com o projeto inteiro
                              dentro. O `truncate` recortava só no fim da
                              linha, então numa tela larga a novidade ocupava
                              a faixa toda e o valor e a data eram empurrados
                              para longe do olho. O `truncate` fica como
                              segunda rede, para a tela estreita. */}
                          <span className="truncate text-sm text-ink">
                            {recortarTexto(humanizarCaixa(n.titulo), 80).trecho}
                          </span>
                        </p>
                        <p className="mt-0.5 flex flex-wrap gap-x-2 text-[12px] text-ink-3">
                          <span className="font-mono uppercase tracking-[0.04em]">
                            {n.tipo === "captacao" ? "Proposta" : "Recebido"}
                          </span>
                          <span>
                            {n.fonte_rotulo || rotuloFonte(n.fonte)}
                          </span>
                          {/* o município lidera a identificação do registro
                              (§35) e nunca sai como código cru — o repasse
                              costuma chegar da fonte sem o nome */}
                          <span>{municipioPrincipal(n)}</span>
                          {/* a descrição do repasse costuma repetir o órgão que
                              já está no rótulo da fonte ("Fundo Nacional de
                              Saúde") — repetido, ele ocupa a linha sem
                              informar nada */}
                          {descricaoUtil(n) && (
                            <span className="truncate">
                              {recortarTexto(humanizarCaixa(descricaoUtil(n)!), 80).trecho}
                            </span>
                          )}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3 text-sm">
                        {brl(n.valor) && (
                          <span className="tabular-nums">{brl(n.valor)}</span>
                        )}
                        {/* data do item na sua própria safra (data da proposta,
                            data do repasse). Sem data, ao menos o ano — é por
                            ele que o item entrou no recorte. */}
                        {(dataBr(n.data) || n.ano) && (
                          <span className="font-mono text-[12px] text-ink-3">
                            {dataBr(n.data) ?? n.ano}
                          </span>
                        )}
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {noticias.length > 0 && (
            <section className="flex flex-col gap-3">
              <h2 className="tracking-tight">Painel informativo — TransfereGov</h2>
              <ol className="card divide-y divide-hairline p-0">
                {noticias.map((n, i) => (
                  <li key={i}>
                    <a
                      href={n.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex flex-col gap-0.5 px-5 py-3.5 row-interactive"
                    >
                      <p className="text-sm text-ink">{n.titulo} ↗</p>
                      {n.resumo && (
                        <p className="line-clamp-1 text-[12px] text-ink-3">
                          {n.resumo}
                        </p>
                      )}
                    </a>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}
    </>
  );
}

export default function MeuPainelPage() {
  return (
    <Suspense fallback={<SkeletonCards />}>
      <MeuPainel />
    </Suspense>
  );
}
