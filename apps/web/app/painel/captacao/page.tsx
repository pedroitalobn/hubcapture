"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FilterChips } from "@/components/FilterChips";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

type Proposta = {
  id: string;
  id_externo: string;
  titulo?: string | null;
  ano?: number | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
};

/** Safra: quantas propostas foram CRIADAS naquele ano (não atualizadas). */
type AnoResumo = {
  ano?: number | null;
  total: number;
  valor_total: string;
};

const SEM_ANO = "Sem ano informado";

/** Agrupa a lista (já ordenada por ano desc pela API) por ano de criação. */
function agruparPorAno(propostas: Proposta[]): [string, Proposta[]][] {
  const grupos = new Map<string, Proposta[]>();
  for (const p of propostas) {
    const chave = p.ano ? String(p.ano) : SEM_ANO;
    const atual = grupos.get(chave);
    if (atual) atual.push(p);
    else grupos.set(chave, [p]);
  }
  return [...grupos.entries()];
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [anos, setAnos] = useState<AnoResumo[]>([]);
  const [anoSel, setAnoSel] = useState<string | null>(null);
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    const [lista, safras] = await Promise.all([
      api.GET("/api/v1/propostas", {
        params: { query: anoSel ? { ano: Number(anoSel) } : {} },
      }),
      api.GET("/api/v1/propostas/anos", { params: { query: {} } }),
    ]);
    if (lista.error || safras.error) {
      setMsg("Falha ao carregar propostas.");
      return;
    }
    setPropostas((lista.data as Proposta[]) ?? []);
    setAnos((safras.data as AnoResumo[]) ?? []);
  }, [anoSel]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

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

  // só anos conhecidos viram chip; a safra sem ano aparece na visão "Todas"
  const chips = useMemo(
    () =>
      anos
        .filter((a) => a.ano != null)
        .map((a) => ({
          value: String(a.ano),
          label: String(a.ano),
          count: a.total,
        })),
    [anos],
  );

  const grupos = useMemo(() => agruparPorAno(propostas), [propostas]);
  const totalPorAno = useMemo(
    () => new Map(anos.map((a) => [a.ano ? String(a.ano) : SEM_ANO, a.valor_total])),
    [anos],
  );

  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">Captação</h1>
        <p className="text-sm text-gray-500">
          Propostas e editais abertos para o seu território, por ano de criação.
        </p>
      </header>

      <form onSubmit={consultarAvulsa} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Consulta avulsa (IBGE, 7 dígitos)
          <input
            value={ibge}
            onChange={(e) => setIbge(e.target.value)}
            placeholder="3550308"
            maxLength={7}
            className="rounded-md border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
          />
        </label>
        <button
          type="submit"
          disabled={carregando || ibge.length !== 7}
          className="rounded-md bg-brand px-4 py-2 text-brand-fg disabled:opacity-60"
        >
          {carregando ? "Consultando…" : "Buscar na fonte"}
        </button>
      </form>

      {msg && <p className="text-sm text-gray-600 dark:text-gray-400">{msg}</p>}

      {chips.length > 0 && (
        <FilterChips options={chips} selected={anoSel} onSelect={setAnoSel} />
      )}

      {propostas.length === 0 ? (
        <p className="text-gray-500">
          {anoSel
            ? `Nenhuma proposta criada em ${anoSel}.`
            : "Nenhuma proposta no cache ainda. Faça uma consulta avulsa acima."}
        </p>
      ) : (
        grupos.map(([ano, itens]) => (
          <section key={ano} className="overflow-x-auto">
            <h2 className="flex flex-wrap items-baseline gap-2 pb-2">
              <span className="text-lg font-semibold">{ano}</span>
              <span className="text-sm text-gray-500">
                {itens.length} proposta{itens.length > 1 ? "s" : ""} ·{" "}
                {formatBRL(totalPorAno.get(ano))}
              </span>
            </h2>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left dark:border-gray-800">
                  <th className="py-2 pr-4">Nº</th>
                  <th className="py-2 pr-4">Título</th>
                  <th className="py-2 pr-4">Município</th>
                  <th className="py-2 pr-4">Valor</th>
                  <th className="py-2 pr-4">Situação</th>
                  <th className="py-2 pr-4"></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-gray-100 dark:border-gray-900"
                  >
                    <td className="py-2 pr-4 font-mono text-xs">{p.id_externo}</td>
                    <td className="py-2 pr-4">{p.titulo ?? "—"}</td>
                    <td className="py-2 pr-4">
                      {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                      {p.uf ? `/${p.uf}` : ""}
                    </td>
                    <td className="py-2 pr-4">{formatBRL(p.valor_total)}</td>
                    <td className="py-2 pr-4">{p.situacao ?? "—"}</td>
                    <td className="py-2 pr-4">
                      <button
                        onClick={() => baixarPdfProposta(p.id)}
                        className="text-xs text-brand underline"
                      >
                        PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </>
  );
}
