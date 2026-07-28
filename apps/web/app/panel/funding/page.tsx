"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api/client";

type Proposta = {
  id: string;
  id_externo: string;
  titulo?: string | null;
  objeto?: string | null;
  descricao?: string | null;
  ano?: number | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
  tipo?: string;
  resumo_ia?: string | null;
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
  status: string;
  erro?: string | null;
};

type Pasta = { id: string; nome: string; cor?: string | null };
type MunicipioPerfil = { ibge: string; nome?: string | null; uf?: string | null };

type Filtros = {
  municipio: string;
  ano: string;
  tipo: "" | "cadastrada" | "disponivel";
  fonte: string;
  area: string;
  situacao: string;
  valorMin: string;
  valorMax: string;
  soFavoritas: boolean;
  pastaId: string;
};

type Aba = { id: string; nome: string; filtros: Filtros };

const FILTROS_VAZIOS: Filtros = {
  municipio: "",
  ano: "",
  tipo: "",
  fonte: "",
  area: "",
  situacao: "",
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

const FONTES = [
  "transferegov_ff",
  "transferegov_esp",
  "transferegov_voluntarias",
  "fns",
  "fnde",
  "serpro",
];

const ABAS_KEY = "hub_captacao_abas";
const ABA_ACOMPANHAMENTO = "acompanhamento";

function formatBRL(v?: string | null): string {
  if (!v) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function num(v?: string | number | null): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** Exercício da proposta. A coluna `ano` vale para toda fonte; `execucao.ano` só
 * existe no relatório do painel TransfereGov e fica como retaguarda. */
function anoDe(p: Proposta): string {
  return String(p.ano ?? p.execucao?.ano ?? "");
}

const ANO_CORRENTE = String(new Date().getFullYear());

function abasIniciais(): Aba[] {
  if (typeof window !== "undefined") {
    try {
      const salvo = window.localStorage.getItem(ABAS_KEY);
      if (salvo) {
        const abas = JSON.parse(salvo) as Aba[];
        // migra abas salvas antes do filtro de município existir
        return abas.map((a) => ({
          ...a,
          filtros: { ...FILTROS_VAZIOS, ...a.filtros },
        }));
      }
    } catch {
      /* estado corrompido → recomeça */
    }
  }
  return [{ id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } }];
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [fontesStatus, setFontesStatus] = useState<FonteStatus[]>([]);
  const [buscando, setBuscando] = useState(true);
  const [favoritos, setFavoritos] = useState<Set<string>>(new Set());
  const [pastas, setPastas] = useState<Pasta[]>([]);
  const [pastaPropostas, setPastaPropostas] = useState<Set<string>>(new Set());
  const [municipios, setMunicipios] = useState<MunicipioPerfil[]>([]);
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

  // Busca em TEMPO REAL: a cada mudança de filtro (debounce), a API consulta as
  // fontes oficiais ao vivo (API pública + scraping via connectors) e devolve
  // as propostas já filtradas + o status por fonte.
  const buscarAoVivo = useCallback(async () => {
    const seq = ++buscaSeq.current;
    setBuscando(true);
    const { data, error } = await api.POST("/api/v1/proposals/live-search", {
      body: {
        municipio_ibge: filtros.municipio || null,
        fonte: filtros.fonte || null,
        area: filtros.area || null,
        situacao: filtros.situacao || null,
        valor_min: filtros.valorMin || null,
        valor_max: filtros.valorMax || null,
        tipo: filtros.tipo || null,
      } as never,
    });
    if (seq !== buscaSeq.current) return; // resposta antiga — descarta
    if (error) {
      setMsg("Falha na busca em tempo real. Tente novamente.");
    } else if (data) {
      const resp = data as { propostas: Proposta[]; fontes: FonteStatus[] };
      setPropostas(resp.propostas ?? []);
      setFontesStatus(resp.fontes ?? []);
      setMsg(null);
    }
    setBuscando(false);
  }, [filtros]);

  useEffect(() => {
    if (acompanhando) return;
    const t = setTimeout(() => void buscarAoVivo(), 500);
    return () => clearTimeout(t);
  }, [buscarAoVivo, acompanhando]);

  const carregarCuradoria = useCallback(async () => {
    const [fav, pas, perf] = await Promise.all([
      api.GET("/api/v1/favorites"),
      api.GET("/api/v1/folders"),
      api.GET("/api/v1/profile"),
    ]);
    if (fav.data) {
      setFavoritos(
        new Set(
          (fav.data as { proposta_id: string }[]).map((f) => f.proposta_id),
        ),
      );
    }
    if (pas.data) setPastas(pas.data as Pasta[]);
    if (perf.data)
      setMunicipios(
        (perf.data as { municipios: MunicipioPerfil[] }).municipios ?? [],
      );
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

  async function alternarFavorito(p: Proposta) {
    if (favoritos.has(p.id)) {
      await api.DELETE("/api/v1/favorites/{proposta_id}", {
        params: { path: { proposta_id: p.id } },
      });
      setFavoritos((prev) => {
        const s = new Set(prev);
        s.delete(p.id);
        return s;
      });
    } else {
      await api.POST("/api/v1/favorites", { body: { proposta_id: p.id } });
      setFavoritos((prev) => new Set(prev).add(p.id));
    }
    if (acompanhando) void carregarAcompanhadas();
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

  const visiveis = useMemo(() => {
    let lista = acompanhando ? acompanhadas : propostas;
    if (filtros.ano) lista = lista.filter((p) => anoDe(p) === filtros.ano);
    if (filtros.soFavoritas) lista = lista.filter((p) => favoritos.has(p.id));
    if (filtros.pastaId) lista = lista.filter((p) => pastaPropostas.has(p.id));
    return lista;
  }, [propostas, acompanhadas, acompanhando, filtros.ano, filtros.soFavoritas, filtros.pastaId, favoritos, pastaPropostas]);

  const anos = useMemo(
    () =>
      Array.from(
        new Set(
          (acompanhando ? acompanhadas : propostas).map(anoDe).filter(Boolean),
        ),
      ).sort((a, b) => b.localeCompare(a)),
    [propostas, acompanhadas, acompanhando],
  );

  // O painel abre no exercício corrente. Se ele não tiver nada mas houver
  // outros anos na busca, mostra o mais recente — dado na tela em vez de uma
  // lista vazia. Roda só uma vez: depois disso o ano é escolha do usuário.
  const anoDefinido = useRef(false);
  useEffect(() => {
    if (anoDefinido.current || acompanhando || buscando) return;
    if (anos.length === 0 || filtros.ano) return;
    anoDefinido.current = true;
    setFiltros({ ano: anos.includes(ANO_CORRENTE) ? ANO_CORRENTE : anos[0] });
    // setFiltros vem do estado de abas e é estável o bastante para este efeito
    // de primeira carga; incluí-lo re-dispararia a cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anos, acompanhando, buscando, filtros.ano]);

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

  const situacoes = useMemo(
    () =>
      Array.from(
        new Set(propostas.map((p) => p.situacao).filter(Boolean) as string[]),
      ).sort(),
    [propostas],
  );

  const fontesOk = fontesStatus.filter((f) => f.status === "ok").length;
  const fontesErro = Array.from(
    new Set(fontesStatus.filter((f) => f.status === "erro").map((f) => f.fonte)),
  );

  return (
    <>
      <header>
        <h1 className="page-title">Captação</h1>
        <p className="mt-1 text-sm text-ink-2">
          Propostas e oportunidades do seu território, consultadas em tempo real
          nas fontes oficiais (API + scraping).
        </p>
      </header>

      {/* abas — várias frentes de trabalho ao mesmo tempo */}
      <div className="flex flex-wrap items-center gap-1.5">
        {abas.map((a) => (
          <span
            key={a.id}
            className={`inline-flex items-center overflow-hidden rounded-t-lg border border-b-0 border-hairline text-sm ${
              a.id === abaAtiva ? "bg-surface-2 font-medium" : "text-ink-2"
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
                className="pr-2 text-ink-3 hover:text-ink"
                aria-label={`Fechar aba ${a.nome}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
        <button
          onClick={() => setAbaAtiva(ABA_ACOMPANHAMENTO)}
          className={`inline-flex items-center rounded-t-lg border border-b-0 border-hairline px-3 py-1.5 text-sm ${
            acompanhando ? "bg-surface-2 font-medium" : "text-ink-2"
          }`}
          title="Propostas favoritadas que você acompanha"
        >
          ★ Acompanhamento
        </button>
        <button onClick={novaAba} className="btn btn-ghost btn-sm" title="Nova aba">
          + aba
        </button>
      </div>

      {/* filtros — cada mudança dispara a busca ao vivo */}
      {!acompanhando && (
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <div className="flex gap-1.5">
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
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1">
          <span className="field-label">Município</span>
          <select
            value={filtros.municipio}
            onChange={(e) => setFiltros({ municipio: e.target.value })}
            className="input w-48"
          >
            <option value="">todos do perfil</option>
            {municipios.map((m) => (
              <option key={m.ibge} value={m.ibge}>
                {m.nome ?? m.ibge}
                {m.uf ? `/${m.uf}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">Ano</span>
          <select
            value={filtros.ano}
            onChange={(e) => setFiltros({ ano: e.target.value })}
            className="input w-28"
          >
            <option value="">todos</option>
            {anos.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">Fonte</span>
          <select
            value={filtros.fonte}
            onChange={(e) => setFiltros({ fonte: e.target.value })}
            className="input w-44"
          >
            <option value="">todas</option>
            {FONTES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">Área</span>
          <select
            value={filtros.area}
            onChange={(e) => setFiltros({ area: e.target.value })}
            className="input w-40"
          >
            <option value="">todas</option>
            {AREAS.map((a) => (
              <option key={a} value={a}>
                {a.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">Situação</span>
          <select
            value={filtros.situacao}
            onChange={(e) => setFiltros({ situacao: e.target.value })}
            className="input w-44"
          >
            <option value="">todas</option>
            {situacoes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
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
        <label className="flex items-center gap-2 pb-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={filtros.soFavoritas}
            onChange={(e) => setFiltros({ soFavoritas: e.target.checked })}
          />
          Só favoritas ★
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">Pasta</span>
          <select
            value={filtros.pastaId}
            onChange={(e) => setFiltros({ pastaId: e.target.value })}
            className="input w-40"
          >
            <option value="">todas</option>
            {pastas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        <button onClick={criarPasta} className="btn btn-ghost btn-sm mb-1">
          + pasta
        </button>
      </div>
      )}

      {/* estado honesto da coleta ao vivo */}
      {!acompanhando && (
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        {buscando ? (
          <span className="label-mono animate-pulse">
            Consultando fontes oficiais em tempo real…
          </span>
        ) : (
          <>
            <span className="label-mono">
              {fontesOk} consulta{fontesOk === 1 ? "" : "s"} ok
            </span>
            {fontesErro.length > 0 && (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] text-amber-600">
                fora do ar agora: {fontesErro.join(", ")}
              </span>
            )}
            <button
              onClick={() => void buscarAoVivo()}
              className="btn btn-ghost btn-sm"
            >
              ↻ Buscar de novo
            </button>
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
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {(
            [
              ["Transferências", String(execucao.transferencias), false],
              ["Valor global", formatBRL(String(execucao.global)), false],
              ["Empenhado", formatBRL(String(execucao.empenhado)), false],
              ["Empenhado a utilizar", formatBRL(String(execucao.aUtilizar)), true],
              ["Pago", formatBRL(String(execucao.pago)), false],
              ["Saldo em conta", formatBRL(String(execucao.saldo)), false],
            ] as const
          ).map(([rotulo, valor, destaque]) => (
            <div
              key={rotulo}
              className={`card p-4 ${destaque ? "ring-1 ring-lime" : ""}`}
            >
              <p className="field-label">{rotulo}</p>
              <p
                className={`mt-1 text-lg tabular-nums tracking-tight ${
                  destaque ? "text-lime" : ""
                }`}
              >
                {valor}
              </p>
              {destaque && (
                <p className="mt-0.5 text-[11px] text-ink-3">
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
                ? "Buscando nas fontes…"
                : "Nenhuma proposta com esses filtros nas fontes consultadas."}
          </p>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-4 py-3 w-8"></th>
                  <th className="px-3 py-3">Proposta</th>
                  <th className="px-3 py-3">Município</th>
                  <th className="px-3 py-3">Valor global</th>
                  <th className="px-3 py-3">Empenhado</th>
                  <th className="px-3 py-3">Situação</th>
                  <th className="px-3 py-3">Pasta</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-hairline last:border-0 hover:bg-surface-2"
                  >
                    <td className="px-4 py-3">
                      <button
                        onClick={() => alternarFavorito(p)}
                        aria-label="Favoritar"
                        className={
                          favoritos.has(p.id) ? "text-amber-500" : "text-ink-3"
                        }
                      >
                        {favoritos.has(p.id) ? "★" : "☆"}
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <Link
                        href={`/panel/funding/${p.id}`}
                        className="font-medium hover:underline"
                      >
                        {p.titulo ?? p.objeto ?? p.id_externo}
                      </Link>
                      {/* sem resumo de IA (provedor opcional), o objeto da
                          fonte já diz do que se trata */}
                      {(p.resumo_ia ?? p.objeto ?? p.descricao) && (
                        <p className="mt-0.5 line-clamp-2 max-w-md text-xs text-ink-3">
                          {p.resumo_ia ?? p.objeto ?? p.descricao}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3 text-ink-2">
                      {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                      {p.uf ? `/${p.uf}` : ""}
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {formatBRL(p.execucao?.valor_global ?? p.valor_total)}
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {p.execucao?.valor_empenhado != null ? (
                        <>
                          {formatBRL(p.execucao.valor_empenhado)}
                          {num(p.execucao.valor_empenhado) > num(p.execucao.valor_pago) && (
                            <span
                              className="ml-1 align-middle text-[10px] text-lime"
                              title="Há verba empenhada ainda não utilizada"
                            >
                              ●
                            </span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-ink-2">{p.situacao ?? "—"}</span>
                      <span
                        className={`ml-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${
                          p.tipo === "disponivel"
                            ? "bg-emerald-500/10 text-emerald-600"
                            : "bg-surface-2 text-ink-3"
                        }`}
                      >
                        {p.tipo === "disponivel" ? "disponível" : "cadastrada"}
                      </span>
                    </td>
                    <td className="px-3 py-3">
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
      </section>
    </>
  );
}
