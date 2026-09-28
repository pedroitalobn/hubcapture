"use client";

/**
 * Oportunidades — programas em que os municípios SELECIONADOS podem e devem
 * se inscrever (§63).
 *
 * O catálogo é o de programas do TransfereGov (pacote SIconv, carga diária) e
 * o recorte é o da barra do painel (§33): cada programa aparece com as janelas
 * abertas, QUAIS dos municípios selecionados podem se inscrever (UF habilitada
 * e ente municipal aceito como proponente) e, quando há, POR QUE deveriam —
 * já propuseram neste programa, o tema casa com as áreas do perfil.
 *
 * O ano não é fixo em lugar nenhum: "aberto" é a janela de recebimento que
 * cobre hoje, venha o programa de que ano vier.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { ModuloGate } from "@/components/ModuloGate";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ChipFiltro, SeletorSimples } from "@/components/kit";
import { Aviso } from "@/components/ui";
import { API_ORIGIN, garantirSessao } from "@/lib/api/client";
import { formatDate, humanizarCaixa, tomPrazo } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

interface Janela {
  tipo: string;
  rotulo: string;
  como: string;
  inicio?: string | null;
  fim: string;
  status: "aberta" | "em_breve";
  dias_restantes: number;
}

interface MunicipioElegivel {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
  historico: boolean;
}

interface Programa {
  id: string;
  codigo?: string | null;
  nome?: string | null;
  orgao_superior?: string | null;
  orgao?: string | null;
  ano?: number | null;
  modalidades: string[];
  naturezas: string[];
  aceita_municipio: boolean;
  janelas: Janela[];
  prazo_final?: string | null;
  dias_restantes?: number | null;
  municipios: MunicipioElegivel[];
  categorias: { slug: string; rotulo: string }[];
  motivos: { chave: string; texto: string }[];
  recomendado: boolean;
  url_consulta: string;
}

interface Faceta {
  valor: string;
  rotulo: string;
  total: number;
}

interface Resposta {
  programas: Programa[];
  total: number;
  recomendados: number;
  encerrando: number;
  municipios: { ibge: string; nome?: string | null; uf?: string | null }[];
  catalogo: { total: number; atualizado_em?: string | null };
  facetas: Record<string, Faceta[]>;
}

/** Consulta de chamamentos públicos (MROSC) — ainda fora do pacote de dados. */
const URL_CHAMAMENTO =
  "https://discricionarias.transferegov.sistema.gov.br/voluntarias/prestacao/mrosc/ChamamentoPublico/chamamentoPublicoConsultaPesquisa.jsf";

const TOM_BADGE = { ok: "success", warn: "warning", danger: "danger" } as const;

async function buscar(params: URLSearchParams): Promise<Resposta> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/opportunities?${params}`, {
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error(`Falha ao consultar as oportunidades (HTTP ${resp.status})`);
  return resp.json();
}

function rotuloPrazo(j: Janela): string {
  if (j.status === "em_breve") {
    return j.dias_restantes === 0 ? "abre hoje" : `abre em ${j.dias_restantes} dia(s)`;
  }
  if (j.dias_restantes === 0) return "encerra hoje";
  if (j.dias_restantes === 1) return "encerra amanhã";
  return `encerra em ${j.dias_restantes} dias`;
}

function Conteudo() {
  const { selecionados, ativos } = useTerritorio();
  const [q, setQ] = useState("");
  const [orgao, setOrgao] = useState("");
  const [categoria, setCategoria] = useState("");
  const [janela, setJanela] = useState("");
  const [recomendados, setRecomendados] = useState(false);
  const [todasNaturezas, setTodasNaturezas] = useState(false);
  const [dados, setDados] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const pedido = useRef(0);

  const params = useMemo(() => {
    const p = new URLSearchParams();
    for (const ibge of paramMunicipio(selecionados) ?? []) p.append("municipio", ibge);
    if (q.trim()) p.set("q", q.trim());
    if (orgao) p.set("orgao", orgao);
    if (categoria) p.set("categoria", categoria);
    if (janela) p.set("janela", janela);
    if (recomendados) p.set("recomendados", "true");
    if (todasNaturezas) p.set("todas_naturezas", "true");
    return p;
  }, [selecionados, q, orgao, categoria, janela, recomendados, todasNaturezas]);

  useEffect(() => {
    const id = ++pedido.current;
    setCarregando(true);
    const t = setTimeout(async () => {
      try {
        const r = await buscar(params);
        if (id !== pedido.current) return; // resposta de um filtro já trocado
        setDados(r);
        setErro(null);
      } catch (e) {
        if (id === pedido.current) {
          setErro(e instanceof Error ? e.message : "Não foi possível consultar agora.");
        }
      } finally {
        if (id === pedido.current) setCarregando(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [params]);

  const recorte =
    ativos.length === 0
      ? "seu território"
      : ativos.length <= 3
        ? ativos.map((m) => m.nome ?? m.ibge).join(", ")
        : `${ativos.length} municípios`;

  const semCatalogo = dados !== null && dados.catalogo.total === 0;
  const filtrosAtivos = Boolean(q || orgao || categoria || janela || recomendados);
  const facetas = dados?.facetas ?? {};

  return (
    <>
      <PageHeader
        titulo="Oportunidades"
        descricao={
          <>
            Programas do TransfereGov com inscrição aberta em que{" "}
            <strong className="text-ink">{recorte}</strong> pode apresentar proposta —
            os recomendados primeiro.
          </>
        }
      />

      {dados && !semCatalogo && (
        <section className="stagger grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Programas abertos"
            value={String(dados.total)}
            context="em que o recorte pode se inscrever"
          />
          <StatCard
            label="Recomendados"
            value={String(dados.recomendados)}
            context="histórico do município ou área do perfil"
            tone={dados.recomendados ? "lime" : undefined}
            onClick={() => setRecomendados((v) => !v)}
            ativo={recomendados}
          />
          <StatCard
            label="Encerrando"
            value={String(dados.encerrando)}
            context="janela fecha em até 15 dias"
          />
        </section>
      )}

      {!semCatalogo && (
        <div className="toolbar flex-wrap">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar programa, código ou órgão…"
            className="input min-w-[220px] flex-1 text-sm"
            aria-label="Buscar programa"
          />
          <SeletorSimples
            rotulo="Órgão"
            valor={orgao}
            vazio="Todos"
            opcoes={(facetas.orgao ?? []).map((f) => ({
              valor: f.valor,
              rotulo: humanizarCaixa(f.rotulo),
              total: f.total,
            }))}
            aoMudar={setOrgao}
          />
          <SeletorSimples
            rotulo="Tema"
            valor={categoria}
            opcoes={facetas.categoria ?? []}
            aoMudar={setCategoria}
          />
          <SeletorSimples
            rotulo="Janela"
            valor={janela}
            opcoes={facetas.janela ?? []}
            aoMudar={setJanela}
          />
          <label className="flex items-center gap-2 text-[13px] text-ink-2">
            <input
              type="checkbox"
              checked={todasNaturezas}
              onChange={(e) => setTodasNaturezas(e.target.checked)}
              className="accent-brand"
            />
            Incluir programas só para OSC/estados
          </label>
        </div>
      )}

      {filtrosAtivos && (
        <div className="flex flex-wrap items-center gap-2">
          {q && <ChipFiltro onRemover={() => setQ("")}>“{q}”</ChipFiltro>}
          {orgao && (
            <ChipFiltro onRemover={() => setOrgao("")}>{humanizarCaixa(orgao)}</ChipFiltro>
          )}
          {categoria && (
            <ChipFiltro onRemover={() => setCategoria("")}>
              {facetas.categoria?.find((f) => f.valor === categoria)?.rotulo ?? categoria}
            </ChipFiltro>
          )}
          {janela && (
            <ChipFiltro onRemover={() => setJanela("")}>
              {facetas.janela?.find((f) => f.valor === janela)?.rotulo ?? janela}
            </ChipFiltro>
          )}
          {recomendados && (
            <ChipFiltro onRemover={() => setRecomendados(false)}>Só recomendados</ChipFiltro>
          )}
        </div>
      )}

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {semCatalogo && (
        <Aviso tom="info">
          O catálogo de programas ainda não foi carregado. Ele chega pela carga
          diária do pacote de dados do TransfereGov (Administração → Pacote
          SIconv). Enquanto isso, a consulta oficial está no fim da página.
        </Aviso>
      )}

      {carregando && !dados && <p className="text-sm text-ink-3">Consultando programas…</p>}

      {dados && !semCatalogo && dados.programas.length === 0 && !carregando && (
        <div className="card p-6 text-sm text-ink-2">
          Nenhum programa aberto para {recorte}
          {filtrosAtivos ? " com esses filtros" : " hoje"}.
          {!todasNaturezas && " Programas exclusivos para OSC ou estados estão ocultos."}
        </div>
      )}

      <section className={`flex flex-col gap-3 ${carregando ? "opacity-60" : ""}`}>
        {dados?.programas.map((p) => (
          <CartaoPrograma key={p.id} p={p} multiplos={(dados?.municipios.length ?? 0) > 1} />
        ))}
      </section>

      <section className="card flex flex-col gap-2 p-5 text-sm text-ink-2">
        <h2 className="label-mono">Chamamentos públicos (MROSC)</h2>
        <p>
          Editais de chamamento para parcerias com organizações da sociedade civil
          ainda não estão no pacote de dados — a consulta é no portal, com os
          filtros “Ano” e “Apto a receber proposta: Sim”.
        </p>
        <a href={URL_CHAMAMENTO} target="_blank" rel="noreferrer" className="link-soft self-start">
          Abrir consulta de chamamentos ↗
        </a>
        {dados?.catalogo.atualizado_em && (
          <p className="text-[12px] text-ink-3">
            Catálogo de programas atualizado em {formatDate(dados.catalogo.atualizado_em)}.
          </p>
        )}
      </section>
    </>
  );
}

function CartaoPrograma({ p, multiplos }: { p: Programa; multiplos: boolean }) {
  const [copiado, setCopiado] = useState(false);
  const principal = p.janelas.find((j) => j.status === "aberta") ?? p.janelas[0];

  async function copiar() {
    if (!p.codigo) return;
    try {
      await navigator.clipboard.writeText(p.codigo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1500);
    } catch {
      /* sem permissão de clipboard — o código segue selecionável */
    }
  }

  return (
    <article className="card flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            {p.recomendado && <StatusBadge tone="success">Recomendado</StatusBadge>}
            {p.categorias.map((c) => (
              <span key={c.slug} className="chip text-[11px]">
                {c.rotulo}
              </span>
            ))}
          </div>
          <h2 className="text-[15px] font-semibold leading-snug text-ink">
            {humanizarCaixa(p.nome) || "Programa sem nome na fonte"}
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-2">
            {humanizarCaixa(p.orgao_superior)}
            {p.orgao && p.orgao !== p.orgao_superior ? ` · ${humanizarCaixa(p.orgao)}` : ""}
          </p>
        </div>
        {principal && (
          <div className="flex flex-col items-end gap-1 text-right">
            <StatusBadge
              tone={
                principal.status === "em_breve"
                  ? "info"
                  : TOM_BADGE[tomPrazo(principal.dias_restantes) ?? "ok"]
              }
            >
              {rotuloPrazo(principal)}
            </StatusBadge>
            <span className="text-[12px] text-ink-3">até {formatDate(principal.fim)}</span>
          </div>
        )}
      </div>

      {p.motivos.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-md bg-brand/10 px-3 py-2 text-[13px] text-ink">
          {p.motivos.map((m) => (
            <li key={m.chave}>✓ {m.texto}</li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 text-[13px] sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <span className="field-label">Como se inscrever</span>
          {p.janelas.map((j) => (
            <p key={j.tipo} className="text-ink-2">
              <strong className="text-ink">{j.rotulo}</strong>{" "}
              {j.inicio ? `${formatDate(j.inicio)} a ` : "até "}
              {formatDate(j.fim)}
              {j.status === "em_breve" && " (ainda não abriu)"}
              <span className="block text-[12px] text-ink-3">{j.como}</span>
            </p>
          ))}
        </div>
        <div className="flex flex-col gap-1">
          <span className="field-label">
            {multiplos ? "Municípios que podem se inscrever" : "Município"}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {p.municipios.map((m) => (
              <span
                key={m.ibge}
                className={`chip text-[12px] ${m.historico ? "chip-active" : ""}`}
                title={m.historico ? "Já apresentou proposta neste programa" : undefined}
              >
                {m.nome ?? m.ibge}
                {m.uf ? `/${m.uf}` : ""}
              </span>
            ))}
          </div>
          {p.naturezas.length > 0 && (
            <p className="text-[12px] text-ink-3">
              Proponentes aceitos: {p.naturezas.join(" · ")}
            </p>
          )}
          {p.modalidades.length > 0 && (
            <p className="text-[12px] text-ink-3">Modalidade: {p.modalidades.join(" · ")}</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-hairline pt-3 text-[13px]">
        {p.codigo && (
          <button
            type="button"
            onClick={() => void copiar()}
            className="font-mono text-[12px] text-ink-2 hover:text-ink"
            title="Copiar o código para buscar no TransfereGov"
          >
            Código {p.codigo} {copiado ? "· copiado" : "· copiar"}
          </button>
        )}
        <a href={p.url_consulta} target="_blank" rel="noreferrer" className="link-soft">
          Consultar no TransfereGov ↗
        </a>
      </div>
    </article>
  );
}

export default function OportunidadesPage() {
  return (
    <ModuloGate modulo="oportunidades" titulo="Oportunidades">
      <Conteudo />
    </ModuloGate>
  );
}
