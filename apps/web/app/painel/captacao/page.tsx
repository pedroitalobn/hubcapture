"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, baixarPdfProposta } from "@/lib/api/client";

type Proposta = {
  id: string;
  id_externo: string;
  titulo?: string | null;
  objeto?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
  tipo?: string;
  resumo_ia?: string | null;
};

type Pasta = { id: string; nome: string; cor?: string | null };

type Filtros = {
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

const ABAS_KEY = "hub_captacao_abas";

function formatBRL(v?: string | null): string {
  if (!v) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function abasIniciais(): Aba[] {
  if (typeof window !== "undefined") {
    try {
      const salvo = window.localStorage.getItem(ABAS_KEY);
      if (salvo) return JSON.parse(salvo) as Aba[];
    } catch {
      /* estado corrompido → recomeça */
    }
  }
  return [{ id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } }];
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [favoritos, setFavoritos] = useState<Set<string>>(new Set());
  const [pastas, setPastas] = useState<Pasta[]>([]);
  const [pastaPropostas, setPastaPropostas] = useState<Set<string>>(new Set());
  const [abas, setAbas] = useState<Aba[]>(abasIniciais);
  const [abaAtiva, setAbaAtiva] = useState<string>(
    () => abasIniciais()[0]?.id ?? "aba-1",
  );
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const aba: Aba = abas.find((a) => a.id === abaAtiva) ??
    abas[0] ?? { id: "aba-1", nome: "Geral", filtros: { ...FILTROS_VAZIOS } };
  const filtros = aba.filtros;

  useEffect(() => {
    window.localStorage.setItem(ABAS_KEY, JSON.stringify(abas));
  }, [abas]);

  const carregar = useCallback(async () => {
    const query: Record<string, string> = {};
    if (filtros.tipo) query.tipo = filtros.tipo;
    if (filtros.fonte) query.fonte = filtros.fonte;
    if (filtros.area) query.area = filtros.area;
    if (filtros.situacao) query.situacao = filtros.situacao;
    if (filtros.valorMin) query.valor_min = filtros.valorMin;
    if (filtros.valorMax) query.valor_max = filtros.valorMax;
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query: query as never },
    });
    if (error) {
      setMsg("Falha ao carregar propostas.");
      return;
    }
    setPropostas((data as Proposta[]) ?? []);
  }, [filtros]);

  const carregarCuradoria = useCallback(async () => {
    const [fav, pas] = await Promise.all([
      api.GET("/api/v1/favoritos"),
      api.GET("/api/v1/pastas"),
    ]);
    if (fav.data) {
      setFavoritos(
        new Set(
          (fav.data as { proposta_id: string }[]).map((f) => f.proposta_id),
        ),
      );
    }
    if (pas.data) setPastas(pas.data as Pasta[]);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);
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
      const { data } = await api.GET("/api/v1/pastas/{pasta_id}/propostas", {
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
      await api.DELETE("/api/v1/favoritos/{proposta_id}", {
        params: { path: { proposta_id: p.id } },
      });
      setFavoritos((prev) => {
        const s = new Set(prev);
        s.delete(p.id);
        return s;
      });
    } else {
      await api.POST("/api/v1/favoritos", { body: { proposta_id: p.id } });
      setFavoritos((prev) => new Set(prev).add(p.id));
    }
  }

  async function criarPasta() {
    const nome = window.prompt("Nome da nova pasta (projeto, área ou região):");
    if (!nome) return;
    const { data } = await api.POST("/api/v1/pastas", { body: { nome } });
    if (data) setPastas((prev) => [...prev, data as Pasta]);
  }

  async function moverParaPasta(propostaId: string, pastaId: string) {
    if (!pastaId) return;
    await api.POST("/api/v1/pastas/{pasta_id}/propostas", {
      params: { path: { pasta_id: pastaId } },
      body: { proposta_id: propostaId },
    });
    if (filtros.pastaId === pastaId)
      setPastaPropostas((prev) => new Set(prev).add(propostaId));
    setMsg("Proposta adicionada à pasta.");
  }

  async function consultarAvulsa(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setCarregando(true);
    const { error } = await api.POST("/api/v1/consulta-avulsa", {
      body: { municipio_ibge: ibge, fonte: "transferegov_ff" },
    });
    if (error) {
      setMsg(
        "A fonte oficial não respondeu agora (comum: API do TransfereGov instável). Tente novamente.",
      );
    } else {
      setMsg("Consulta concluída.");
      await carregar();
    }
    setCarregando(false);
  }

  const visiveis = useMemo(() => {
    let lista = propostas;
    if (filtros.soFavoritas) lista = lista.filter((p) => favoritos.has(p.id));
    if (filtros.pastaId) lista = lista.filter((p) => pastaPropostas.has(p.id));
    return lista;
  }, [propostas, filtros.soFavoritas, filtros.pastaId, favoritos, pastaPropostas]);

  const situacoes = useMemo(
    () =>
      Array.from(
        new Set(propostas.map((p) => p.situacao).filter(Boolean) as string[]),
      ).sort(),
    [propostas],
  );
  const fontes = useMemo(
    () => Array.from(new Set(propostas.map((p) => p.fonte))).sort(),
    [propostas],
  );

  return (
    <>
      <header>
        <h1 className="page-title">Captação</h1>
        <p className="mt-1 text-sm text-ink-2">
          Propostas cadastradas e oportunidades disponíveis para o seu território.
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
        <button onClick={novaAba} className="btn btn-ghost btn-sm" title="Nova aba">
          + aba
        </button>
      </div>

      {/* filtros — granularidade do painel BI, entregue simples */}
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
          <span className="field-label">Fonte</span>
          <select
            value={filtros.fonte}
            onChange={(e) => setFiltros({ fonte: e.target.value })}
            className="input w-40"
          >
            <option value="">todas</option>
            {fontes.map((f) => (
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

      <form onSubmit={consultarAvulsa} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Consulta avulsa (IBGE, 7 dígitos)</span>
          <input
            value={ibge}
            onChange={(e) => setIbge(e.target.value)}
            placeholder="3550308"
            maxLength={7}
            className="input w-48"
          />
        </label>
        <button
          type="submit"
          disabled={carregando || ibge.length !== 7}
          className="btn btn-primary"
        >
          {carregando ? "Consultando…" : "Buscar na fonte"}
        </button>
      </form>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <section className="overflow-x-auto">
        {visiveis.length === 0 ? (
          <p className="text-ink-3">
            Nenhuma proposta com esses filtros. Ajuste os filtros ou faça uma
            consulta avulsa acima.
          </p>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-4 py-3 w-8"></th>
                  <th className="px-3 py-3">Proposta</th>
                  <th className="px-3 py-3">Município</th>
                  <th className="px-3 py-3">Valor</th>
                  <th className="px-3 py-3">Situação</th>
                  <th className="px-3 py-3">Pasta</th>
                  <th className="px-3 py-3"></th>
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
                        href={`/painel/captacao/${p.id}`}
                        className="font-medium hover:underline"
                      >
                        {p.titulo ?? p.objeto ?? p.id_externo}
                      </Link>
                      {p.resumo_ia && (
                        <p className="mt-0.5 line-clamp-2 max-w-md text-xs text-ink-3">
                          {p.resumo_ia}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3 text-ink-2">
                      {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                      {p.uf ? `/${p.uf}` : ""}
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {formatBRL(p.valor_total)}
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
                    <td className="px-3 py-3">
                      <button
                        onClick={() => baixarPdfProposta(p.id)}
                        className="btn btn-ghost btn-sm"
                      >
                        PDF
                      </button>
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
