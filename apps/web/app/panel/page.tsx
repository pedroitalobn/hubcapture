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
import { formatBRL, humanizarCaixa, recortarTexto } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

// ── Panorama financeiro do território (números + gráfico) ───────────────────
// Reusa /proposals/summary (mesma fonte da página de resumo da Captação) para
// dar cards e um gráfico por ano direto no Meu painel. A safra vem do filtro da
// PÁGINA (prop `ano`), não de um seletor próprio: dois filtros de ano na mesma
// tela mostravam recortes diferentes lado a lado — o gráfico obedecia a um, os
// cards e o feed continuavam no outro.
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
}

function numBR(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

function PanoramaFinanceiro({ ano }: { ano: string }) {
  const { selecionados } = useTerritorio();
  const [resumo, setResumo] = useState<ResumoPainelData | null>(null);
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
  const maxAno = Math.max(
    1,
    ...porAno.flatMap((a) => [numBR(a.aprovado), numBR(a.desembolsado)]),
  );

  return (
    <section className="anim-fade-up flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="tracking-tight">Panorama financeiro</h2>
        <span className="label-mono">
          {ano ? `safra ${ano}` : "todas as safras"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total geral"
          value={formatBRL(resumo.cards.valor_conveniado)}
          context={`${resumo.cards.transferencias} transferências`}
        />
        <StatCard
          label="Empenhado"
          value={formatBRL(resumo.cards.valor_empenhado)}
          context="reservado pelo concedente"
        />
        {/* "Publicado" vem da fonte ora como valor, ora como estado. Com
            valor, mostra o valor; sem ele, a contagem de publicadas — R$ 0,00
            leria como "nada publicado", que é outra coisa. */}
        <StatCard
          label="Publicado"
          value={
            numBR(resumo.cards.valor_publicado) > 0
              ? formatBRL(resumo.cards.valor_publicado)
              : String(resumo.cards.propostas_publicadas)
          }
          context={
            numBR(resumo.cards.valor_publicado) > 0
              ? "publicado pela fonte"
              : "propostas publicadas"
          }
        />
        <StatCard
          label="Pago"
          value={formatBRL(resumo.cards.valor_pago)}
          context="efetivamente pago"
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
  municipio_nome?: string | null;
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

/** Preferência salva do filtro de ano ("" = todos os anos). */
function lerAnoSalvo(): string {
  if (typeof window === "undefined") return "";
  try {
    const salvo = window.localStorage.getItem(ANO_KEY);
    return salvo && /^\d{4}$/.test(salvo) ? salvo : "";
  } catch {
    return ""; // preferência corrompida/indisponível → todos os anos
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
  const [favoritas, setFavoritas] = useState<Set<string>>(new Set());
  const [favErro, setFavErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const tentativas = useRef(0);
  // "" = todos os anos. Ler o localStorage já no initializer divergiria do HTML
  // do servidor, que não tem acesso a ele — erro de hidratação; a restauração
  // acontece no efeito abaixo.
  const [ano, setAno] = useState("");
  const prefCarregada = useRef(false);

  // O recorte de município E a safra entram em TODA consulta do painel: trocar
  // o território no trilho lateral ou o ano no filtro refaz visão geral,
  // panorama e feed — todos no mesmo recorte.
  const carregar = useCallback(async () => {
    const municipio = paramMunicipio(selecionados);
    const query = { municipio, ano: ano || undefined };
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
  }, [selecionados, ano]);

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
    const salvo = lerAnoSalvo();
    if (salvo) setAno(salvo);
    prefCarregada.current = true;
  }, []);

  // Persiste a escolha. O guard evita o efeito rodar ANTES da restauração e
  // gravar o padrão por cima do que o usuário já tinha escolhido.
  useEffect(() => {
    if (!prefCarregada.current) return;
    try {
      window.localStorage.setItem(ANO_KEY, ano);
    } catch {
      /* storage cheio/bloqueado: o filtro segue valendo nesta sessão */
    }
  }, [ano]);

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
  // zerado) prenderia o painel num recorte vazio — volta para "todos os anos".
  useEffect(() => {
    if (!ano || !novidades) return;
    if (!(novidades.anos ?? []).some((a) => a.ano === ano)) setAno("");
  }, [ano, novidades]);
  const dimensoes = data?.dimensoes ?? [];
  // Dimensões que não têm safra (conformidade/obras): o painel avisa em vez de
  // deixar o usuário achar que o filtro falhou nesses cards.
  const semSafra = ano
    ? dimensoes.filter((d) => d.recorte_ano === false).map((d) => d.titulo)
    : [];
  // Safras em chip (as mais recentes) × safras antigas (dropdown compacto).
  const anosChip = anosDisponiveis.slice(0, ANOS_EM_CHIP);
  const anosAntigos = anosDisponiveis.slice(ANOS_EM_CHIP);
  const anoAntigo = anosAntigos.some((a) => a.ano === ano);
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
        {/* Filtro de ano da PÁGINA: cards, panorama e novidades no mesmo
            recorte. Chips à esquerda, sob o título — o ativo leva o acento da
            marca, então a safra em vigor está sempre à vista. Só aparece
            quando o território tem alguma safra — filtro que não muda nada
            parece quebrado. */}
        {!semTerritorio && anosDisponiveis.length > 0 && (
          <nav
            aria-label="Filtrar o painel por safra (ano)"
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
                  onClick={() => setAno("")}
                  className={`chip ${!ano ? "chip-active" : ""}`}
                  aria-pressed={!ano}
                  title="Painel inteiro, sem recorte de safra"
                >
                  Todos os anos
                </button>
                {anosChip.map((a) => (
                  <button
                    key={a.ano}
                    type="button"
                    onClick={() => setAno(a.ano)}
                    className={`chip ${ano === a.ano ? "chip-active" : ""}`}
                    aria-pressed={ano === a.ano}
                    title={`Recorta o painel inteiro pela safra ${a.ano}`}
                  >
                    {a.ano}
                    <span className="tabular-nums opacity-60">{a.total}</span>
                  </button>
                ))}
                {anosAntigos.length > 0 && (
                  <select
                    value={anoAntigo ? ano : ""}
                    onChange={(e) => e.target.value && setAno(e.target.value)}
                    className={`chip ${anoAntigo ? "chip-active" : ""}`}
                    title="Safras mais antigas do território"
                  >
                    <option value="">anteriores…</option>
                    {anosAntigos.map((a) => (
                      <option key={a.ano} value={a.ano}>
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
                    <div
                      className={`text-[44px] font-medium leading-none tracking-[-0.03em] tabular-nums ${
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
                      className="card card-hover group flex flex-1 flex-col justify-between p-6 min-h-44"
                    >
                      {conteudo}
                    </Link>
                  ) : (
                    <div className="card flex flex-1 flex-col justify-between p-6 min-h-44">
                      {conteudo}
                    </div>
                  )}
                  {quebras}
                </div>
              );
            })}
          </section>

          {semSafra.length > 0 && (
            <p className="text-[12px] text-ink-3">
              {semSafra.join(" e ")}{" "}
              {semSafra.length === 1 ? "mostra" : "mostram"} o estado atual do
              município — {semSafra.length === 1 ? "não tem" : "não têm"} recorte
              por ano.
            </p>
          )}

          <PanoramaFinanceiro ano={ano} />

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
                      .map((f) => FONTE_LABEL[f.fonte ?? ""] ?? f.fonte)
                      .join(", ")}
                    ). Novas tentativas rodam no próximo ciclo; você também pode
                    disparar uma busca nas páginas de cada dimensão.
                  </p>
                ) : ano ? (
                  <p>
                    Nenhuma novidade de {ano} no território —{" "}
                    <button
                      type="button"
                      onClick={() => setAno("")}
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
              <ol className="card stagger divide-y divide-hairline p-0">
                {itens.map((n, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 pr-3 row-interactive"
                  >
                    {/* favoritar e exportar direto do painel (só propostas de
                        captação — repasse não tem espelho) */}
                    {n.proposta_id && (
                      <span className="flex shrink-0 items-center gap-2 pl-4">
                        <Favorito
                          ativo={favoritas.has(n.proposta_id)}
                          onToggle={() => alternarFavorita(n.proposta_id!)}
                          rotuloOff="Favoritar esta proposta"
                        />
                        <BotaoEspelho propostaId={n.proposta_id} formato="icone" />
                      </span>
                    )}
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
                          <span>{FONTE_LABEL[n.fonte] ?? n.fonte}</span>
                          {n.municipio_nome && (
                            <span>{humanizarCaixa(n.municipio_nome)}</span>
                          )}
                          {n.descricao && (
                            <span className="truncate">
                              {recortarTexto(humanizarCaixa(n.descricao), 80).trecho}
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
