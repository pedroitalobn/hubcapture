"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api/client";
import { formatBRL, humanizarCaixa } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

// ── Panorama financeiro do território (números + gráfico) ───────────────────
// Reusa /proposals/summary (mesma fonte da página de resumo da Captação) para
// dar cards e um gráfico por ano direto no Meu painel, com filtro de período.
interface ResumoPainelData {
  cards: {
    valor_conveniado: string;
    valor_desembolsado: string;
    valor_a_utilizar: string;
    transferencias: number;
    convenios_em_execucao: number;
    oportunidades_abertas: number;
  };
  por_ano: { ano: string; aprovado: string; desembolsado: string }[];
}

function numBR(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

function PanoramaFinanceiro() {
  const { selecionados } = useTerritorio();
  const [resumo, setResumo] = useState<ResumoPainelData | null>(null);
  const [ano, setAno] = useState("");
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    setCarregando(true);
    void api
      .GET("/api/v1/proposals/summary", {
        params: {
          query: {
            ano: ano || undefined,
            municipio: paramMunicipio(selecionados),
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
  }, [ano, selecionados]);

  if (carregando && !resumo) return <SkeletonCards />;
  if (!resumo) return null;

  const porAno = resumo.por_ano ?? [];
  const anos = porAno.map((a) => a.ano);
  const maxAno = Math.max(
    1,
    ...porAno.flatMap((a) => [numBR(a.aprovado), numBR(a.desembolsado)]),
  );

  return (
    <section className="anim-fade-up flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="tracking-tight">Panorama financeiro</h2>
        <select
          value={ano}
          onChange={(e) => setAno(e.target.value)}
          className="input w-36"
          title="Filtrar por período (ano)"
        >
          <option value="">Todos os anos</option>
          {anos.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Valor conveniado"
          value={formatBRL(resumo.cards.valor_conveniado)}
          context={`${resumo.cards.transferencias} transferências`}
        />
        <StatCard
          label="Desembolsado"
          value={formatBRL(resumo.cards.valor_desembolsado)}
          context="liberado ao ente"
        />
        <StatCard
          label="Em execução"
          value={String(resumo.cards.convenios_em_execucao)}
          context="convênios vigentes"
        />
        <StatCard
          label="Oportunidades abertas"
          value={String(resumo.cards.oportunidades_abertas)}
          context="disponíveis p/ captar"
        />
      </div>

      {porAno.length > 0 && (
        <div className="card p-5">
          <h3 className="label-mono">Aprovado × desembolsado por ano</h3>
          <div className="mt-4 flex items-end gap-2 overflow-x-auto">
            {porAno.map((a) => (
              <div key={a.ano} className="flex min-w-[42px] flex-col items-center gap-1">
                <div className="flex h-28 items-end gap-0.5">
                  <div
                    title={`Aprovado: ${formatBRL(a.aprovado)}`}
                    className="w-3 rounded-t bg-ink/70"
                    style={{ height: `${(numBR(a.aprovado) / maxAno) * 100}%` }}
                  />
                  <div
                    title={`Desembolsado: ${formatBRL(a.desembolsado)}`}
                    className="w-3 rounded-t bg-lime"
                    style={{ height: `${(numBR(a.desembolsado) / maxAno) * 100}%` }}
                  />
                </div>
                <span className="font-mono text-[10px] text-ink-3">{a.ano}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 font-mono text-[11px] text-ink-3">
            <span className="mr-3">▊ aprovado</span>
            <span className="text-lime">▊ desembolsado</span>
          </p>
        </div>
      )}
    </section>
  );
}

interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  href: string;
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
  fonte: string;
  municipio_nome?: string | null;
  href: string;
  proposta_id?: string | null;
}
interface SyncRunStatus {
  fonte?: string | null;
  status?: string | null;
  registros?: number | null;
  finalizado_em?: string | null;
}
interface Novidades {
  itens: Novidade[];
  sync_runs: SyncRunStatus[];
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
interface Oportunidade {
  id: string;
  id_externo: string;
  titulo?: string | null;
  objeto?: string | null;
  fonte: string;
  municipio_nome?: string | null;
  municipio_ibge?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
}

const FONTE_LABEL: Record<string, string> = {
  transferegov_ff: "TransfereGov FF",
  transferegov_esp: "TransfereGov Especiais",
  transferegov_voluntarias: "TransfereGov Voluntárias",
  fpm: "FPM",
  emendas: "Emendas",
  fns: "FNS",
  fnde: "FNDE",
  siconfi: "Siconfi/CAUC",
  sismob: "SISMOB",
  simec: "SIMEC",
  caixa: "CAIXA",
};

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

// ── Filtro de ano das novidades ─────────────────────────────────────────────
// Pills derivadas dos anos que EXISTEM no feed carregado (mais recentes
// primeiro) + "Outros" para o excedente e itens sem data. Pill de ano sem
// nenhum item não é renderizada — filtro que nunca muda a lista parece
// quebrado. A escolha do usuário PERSISTE entre visitas; sem preferência
// salva, abre no ano mais recente com dados.
const ANOS_KEY = "hub_painel_anos";
const OUTROS = "outros";
const MAX_PILLS_ANO = 4;
// Janela pedida à API: o padrão de 20 itens só alcança o ano corrente, o que
// deixava as pills dos anos anteriores permanentemente vazias.
const FEED_LIMITE = 120;

/** Ano do item pelo prefixo do ISO (YYYY-MM-DD); null se ausente/inválido. */
function anoDoItem(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ano = Number(iso.slice(0, 4));
  return Number.isInteger(ano) && ano > 1900 ? ano : null;
}

/**
 * Lê a preferência salva. A validação fina (a pill ainda existe no feed de
 * hoje?) acontece na seleção efetiva, porque o conjunto de pills agora depende
 * dos DADOS carregados — aqui só se descarta lixo estrutural.
 */
function lerAnosSalvos(): string[] | null {
  if (typeof window === "undefined") return null;
  try {
    const salvo = window.localStorage.getItem(ANOS_KEY);
    if (!salvo) return null;
    const bruto = JSON.parse(salvo) as unknown;
    if (!Array.isArray(bruto)) return null;
    const limpo = bruto.filter(
      (c): c is string => typeof c === "string" && (c === OUTROS || /^\d{4}$/.test(c)),
    );
    return limpo.length > 0 ? limpo : null;
  } catch {
    return null; // preferência corrompida → volta ao padrão
  }
}

function MeuPainel() {
  const searchParams = useSearchParams();
  const sincronizando = searchParams.get("sync") === "1";
  // recorte de município escolhido no trilho lateral (vazio = todo o território)
  const { selecionados } = useTerritorio();

  const [data, setData] = useState<VisaoGeral | null>(null);
  const [novidades, setNovidades] = useState<Novidades | null>(null);
  const [noticias, setNoticias] = useState<Noticia[]>([]);
  const [naoLidos, setNaoLidos] = useState(0);
  const [oportunidades, setOportunidades] = useState<Oportunidade[]>([]);
  const [buscandoOportunidades, setBuscandoOportunidades] = useState(true);
  const [favoritas, setFavoritas] = useState<Set<string>>(new Set());
  const [favErro, setFavErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const tentativas = useRef(0);
  // null = usuário ainda não escolheu nada (nem nesta sessão nem salvo) — a
  // seleção efetiva cai no padrão. Ler o localStorage já no initializer
  // divergiria do HTML do servidor, que não tem acesso a ele — erro de
  // hidratação; a restauração acontece no efeito abaixo.
  const [anosSel, setAnosSel] = useState<string[] | null>(null);
  const prefCarregada = useRef(false);

  // O recorte de município entra em TODA consulta do painel: trocar o
  // território no trilho lateral refaz visão geral, feed e oportunidades.
  const carregar = useCallback(async () => {
    const municipio = paramMunicipio(selecionados);
    const [{ data: vg }, { data: nov }] = await Promise.all([
      api.GET("/api/v1/profile/overview", { params: { query: { municipio } } }),
      api.GET("/api/v1/profile/feed", {
        params: { query: { municipio, limite: FEED_LIMITE } },
      }),
    ]);
    if (vg) setData(vg as VisaoGeral);
    if (nov) setNovidades(nov as Novidades);
    setLoading(false);
    // `?.itens.length` protegia contra `nov` ausente mas NÃO contra `itens`
    // ausente — um nível a menos de defesa do que o próprio `?.` pretendia.
    // Sem o segundo `?.`, um feed sem `itens` derruba a tela inicial inteira.
    return (nov as Novidades | undefined)?.itens?.length ?? 0;
  }, [selecionados]);

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
    // Oportunidades DISPONÍVEIS para o território, em TEMPO REAL: a API
    // consulta as fontes ao vivo (live-search) filtrando tipo=disponivel.
    setBuscandoOportunidades(true);
    void (async () => {
      const [ls, fav] = await Promise.all([
        api.POST("/api/v1/proposals/live-search", {
          body: {
            tipo: "disponivel",
            municipios_ibge: paramMunicipio(selecionados) ?? null,
          } as never,
        }),
        api.GET("/api/v1/favorites"),
      ]);
      if (ls.data)
        setOportunidades(
          ((ls.data as { propostas: Oportunidade[] }).propostas ?? []).slice(0, 6),
        );
      if (fav.data)
        setFavoritas(
          new Set(
            (fav.data as { proposta_id: string }[]).map((f) => f.proposta_id),
          ),
        );
      setBuscandoOportunidades(false);
    })();
  }, [selecionados]);

  // Restaura a preferência salva uma única vez, no cliente.
  useEffect(() => {
    const salvo = lerAnosSalvos();
    if (salvo) setAnosSel(salvo);
    prefCarregada.current = true;
  }, []);

  // Persiste a escolha. O guard evita o efeito rodar ANTES da restauração e
  // gravar o padrão por cima do que o usuário já tinha escolhido; null é
  // "nenhuma escolha ainda" e não merece linha no storage.
  useEffect(() => {
    if (!prefCarregada.current || anosSel == null) return;
    try {
      window.localStorage.setItem(ANOS_KEY, JSON.stringify(anosSel));
    } catch {
      /* storage cheio/bloqueado: o filtro segue valendo nesta sessão */
    }
  }, [anosSel]);

  function alternarAno(chave: string) {
    const marcado = anosAtivos.includes(chave);
    // Nunca deixa a seleção vazia: sem nenhuma pill ativa a lista ficaria
    // vazia sem o usuário ter pedido isso, parecendo perda de dados.
    if (marcado && anosAtivos.length === 1) return;
    setAnosSel(
      marcado ? anosAtivos.filter((c) => c !== chave) : [...anosAtivos, chave],
    );
  }

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
  // Pills a partir do que EXISTE no feed: os anos com item, do mais recente ao
  // mais antigo (janela de MAX_PILLS_ANO), + "Outros" quando sobra ano fora da
  // janela ou item sem data. Toda pill renderizada tem ≥1 item por construção.
  const { janelaAnos, pillsAno } = useMemo(() => {
    const anos = new Set<number>();
    let semData = false;
    for (const n of itens) {
      const ano = anoDoItem(n.data);
      if (ano == null) semData = true;
      else anos.add(ano);
    }
    const ordenados = [...anos].sort((a, b) => b - a).map(String);
    const janela = ordenados.slice(0, MAX_PILLS_ANO);
    const temOutros = semData || ordenados.length > janela.length;
    return {
      janelaAnos: janela,
      pillsAno: temOutros ? [...janela, OUTROS] : janela,
    };
  }, [itens]);
  // Chave de filtro do item: o próprio ano quando está na janela, senão OUTROS
  // — item sem data cai em OUTROS de propósito, para continuar alcançável.
  const chaveDoItem = useCallback(
    (iso: string | null | undefined): string => {
      const ano = anoDoItem(iso);
      return ano != null && janelaAnos.includes(String(ano)) ? String(ano) : OUTROS;
    },
    [janelaAnos],
  );
  // Seleção EFETIVA: interseção da escolha do usuário com as pills que o feed
  // de hoje sustenta. Escolha vazia/obsoleta → padrão = ano mais recente com
  // dados (nunca um filtro que esconderia tudo sem motivo aparente).
  const anosAtivos = useMemo(() => {
    const [maisRecente] = pillsAno;
    if (maisRecente == null) return [];
    const escolhidos = (anosSel ?? []).filter((c) => pillsAno.includes(c));
    return escolhidos.length > 0 ? escolhidos : [maisRecente];
  }, [anosSel, pillsAno]);
  // Quantos itens cada pill representa — mostra de cara em que ano há novidade,
  // e deixa explícito o que está sendo escondido pelo filtro.
  const contagemPorAno = useMemo(() => {
    const mapa = new Map<string, number>();
    for (const n of itens) {
      const k = chaveDoItem(n.data);
      mapa.set(k, (mapa.get(k) ?? 0) + 1);
    }
    return mapa;
  }, [itens, chaveDoItem]);
  // Com uma pill só o filtro não filtra nada — a linha some e a lista é tudo.
  const itensFiltrados = useMemo(
    () =>
      pillsAno.length < 2
        ? itens
        : itens.filter((n) => anosAtivos.includes(chaveDoItem(n.data))),
    [itens, pillsAno, anosAtivos, chaveDoItem],
  );
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
            {(data?.dimensoes ?? []).map((d) => (
              <Link
                key={d.chave}
                href={d.href}
                className="card card-hover group flex flex-col justify-between p-6 min-h-44"
              >
                <div className="flex items-start justify-between">
                  <h2 className="tracking-tight">{d.titulo}</h2>
                  <span className="flex h-9 w-9 translate-y-1 items-center justify-center rounded-lg bg-lime text-abyss opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
                    →
                  </span>
                </div>
                <div>
                  <div
                    className={`text-[44px] font-medium leading-none tracking-[-0.03em] tabular-nums ${
                      d.total > 0 ? "text-gradient" : ""
                    }`}
                  >
                    {d.total}
                  </div>
                  <p className="mt-2 text-sm text-ink-2">{d.destaque ?? "—"}</p>
                </div>
              </Link>
            ))}
          </section>

          <PanoramaFinanceiro />

          <section className="anim-fade-up flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="tracking-tight">Últimas novidades no seu território</h2>
              {aguardandoDados && (
                <span className="label-mono animate-pulse">
                  Sincronizando fontes…
                </span>
              )}
            </div>

            {/* Filtro por ano — multisseleção sobre os anos COM novidade no
                feed (+ "Outros"). Com menos de duas pills não há o que
                filtrar, então a linha nem aparece. */}
            {pillsAno.length >= 2 && (
              <div
                role="group"
                aria-label="Filtrar novidades por ano"
                className="flex flex-wrap items-center gap-2"
              >
                {pillsAno.map((chave) => {
                  const ativo = anosAtivos.includes(chave);
                  const total = contagemPorAno.get(chave) ?? 0;
                  const rotulo = chave === OUTROS ? "Outros" : chave;
                  return (
                    <button
                      key={chave}
                      type="button"
                      onClick={() => alternarAno(chave)}
                      aria-pressed={ativo}
                      title={
                        chave === OUTROS
                          ? "Demais anos e itens sem data"
                          : `Novidades de ${chave} (${total})`
                      }
                      className={`chip ${ativo ? "chip-active" : ""}`}
                    >
                      {rotulo}
                      {/* Contagem como BADGE, não texto solto — colada no
                          rótulo, "2026 20" lia como um ano quebrado. */}
                      <span
                        className={`rounded-full px-1.5 py-px text-[10px] leading-4 tabular-nums ${
                          ativo ? "bg-abyss/10" : "bg-surface-2 text-ink-3"
                        }`}
                      >
                        {total}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

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
                      .map((f) => FONTE_LABEL[f.fonte ?? ""] ?? f.fonte)
                      .join(", ")}
                    ). Novas tentativas rodam no próximo ciclo; você também pode
                    disparar uma busca nas páginas de cada dimensão.
                  </p>
                ) : (
                  <p>
                    Nenhuma novidade ainda — os dados chegam após a primeira
                    coleta das fontes do seu perfil.
                  </p>
                )}
              </div>
            ) : (
              <ol className="card stagger divide-y divide-hairline p-0">
                {itensFiltrados.map((n, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 pr-3 transition-colors hover:bg-surface-2"
                  >
                    {/* favoritar e exportar direto do painel (só propostas de
                        captação — repasse não tem espelho) */}
                    {n.proposta_id && (
                      <span className="flex shrink-0 items-center gap-2 pl-4">
                        <button
                          onClick={() => void alternarFavorita(n.proposta_id!)}
                          aria-label="Favoritar"
                          title={
                            favoritas.has(n.proposta_id)
                              ? "Desfavoritar"
                              : "Favoritar esta proposta"
                          }
                          className={`text-lg ${
                            favoritas.has(n.proposta_id)
                              ? "text-warn"
                              : "text-ink-3 hover:text-warn"
                          }`}
                        >
                          {favoritas.has(n.proposta_id) ? "★" : "☆"}
                        </button>
                        <BotaoEspelho propostaId={n.proposta_id} formato="icone" />
                      </span>
                    )}
                    <Link
                      href={n.href}
                      className="flex flex-1 flex-col gap-1 px-2 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-ink">
                          {humanizarCaixa(n.titulo)}
                        </p>
                        <p className="mt-0.5 flex flex-wrap gap-x-2 text-[12px] text-ink-3">
                          <span className="font-mono uppercase tracking-[0.04em]">
                            {n.tipo === "captacao" ? "Captação" : "Recebido"}
                          </span>
                          <span>{FONTE_LABEL[n.fonte] ?? n.fonte}</span>
                          {n.municipio_nome && (
                            <span>{humanizarCaixa(n.municipio_nome)}</span>
                          )}
                          {n.descricao && (
                            <span className="truncate">
                              {humanizarCaixa(n.descricao)}
                            </span>
                          )}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3 text-sm">
                        {brl(n.valor) && (
                          <span className="tabular-nums">{brl(n.valor)}</span>
                        )}
                        {dataBr(n.data) && (
                          <span className="font-mono text-[12px] text-ink-3">
                            {dataBr(n.data)}
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
                      className="flex flex-col gap-0.5 px-5 py-3.5 transition-colors hover:bg-surface-2"
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
