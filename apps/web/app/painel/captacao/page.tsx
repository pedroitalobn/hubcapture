"use client";

import { useCallback, useEffect, useState } from "react";
import { NumeroProposta } from "@/components/NumeroProposta";
import { StatusBadge } from "@/components/StatusBadge";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatBRL, formatDate } from "@/lib/format";

type Proposta = {
  id: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  data_atualizacao_fonte?: string | null;
  fonte: string;
};

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [busca, setBusca] = useState("");
  const [numeroFiltro, setNumeroFiltro] = useState("");
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async (numero: string) => {
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query: numero ? { numero } : {} },
    });
    if (error) {
      setMsg("Falha ao carregar propostas.");
      return;
    }
    setPropostas((data as Proposta[]) ?? []);
  }, []);

  // a busca pelo número vai ao servidor (filtra o cache inteiro, não só a
  // página carregada) — com debounce para não disparar a cada tecla.
  useEffect(() => {
    const t = window.setTimeout(() => setNumeroFiltro(busca.trim()), 350);
    return () => window.clearTimeout(t);
  }, [busca]);

  useEffect(() => {
    void carregar(numeroFiltro);
  }, [carregar, numeroFiltro]);

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
      await carregar(numeroFiltro);
    }
    setCarregando(false);
  }

  const buscando = numeroFiltro.length > 0;
  const unica = buscando && propostas.length === 1 ? propostas[0] : null;

  return (
    <>
      <header className="sticky top-0 z-10 flex flex-col gap-3 border-b border-gray-200 bg-white/90 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-950/90">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Captação</h1>
            <p className="text-sm text-gray-500">
              Propostas e editais abertos para o seu território.
            </p>
          </div>

          {/* Busca pelo NR_PROPOSTA — é o número que o gestor tem em mãos. */}
          <label className="flex w-full max-w-xs flex-col gap-1 text-xs text-gray-500">
            Buscar pelo nº da proposta
            <div className="flex items-center gap-2">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="ex.: 043210/2025"
                inputMode="search"
                className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              />
              {buscando && (
                <button
                  type="button"
                  onClick={() => setBusca("")}
                  className="shrink-0 text-xs underline"
                >
                  limpar
                </button>
              )}
            </div>
          </label>
        </div>

        {/* O número procurado fica fixo no header, junto do resultado. */}
        {buscando && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <NumeroProposta
              numero={unica?.numero_proposta}
              fallback={unica?.id_externo ?? numeroFiltro}
              termo={numeroFiltro}
              size="lg"
            />
            {unica ? (
              <span className="min-w-0 truncate text-gray-600 dark:text-gray-400">
                {unica.titulo ?? unica.objeto ?? "—"}
              </span>
            ) : (
              <span className="text-gray-500">
                {propostas.length} proposta{propostas.length === 1 ? "" : "s"} com esse
                número
              </span>
            )}
          </div>
        )}
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

      <section className="flex flex-col gap-3">
        {propostas.length === 0 ? (
          <p className="text-gray-500">
            {buscando
              ? `Nenhuma proposta com o número “${numeroFiltro}” no cache. Faça uma consulta avulsa do município para trazer da fonte.`
              : "Nenhuma proposta no cache ainda. Faça uma consulta avulsa acima."}
          </p>
        ) : (
          propostas.map((p) => (
            <article
              key={p.id}
              className="rounded-lg border border-gray-200 p-4 dark:border-gray-800"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <NumeroProposta
                    numero={p.numero_proposta}
                    fallback={p.id_externo}
                    termo={numeroFiltro}
                  />
                  <StatusBadge tone="info">{p.fonte}</StatusBadge>
                  {p.situacao && <StatusBadge>{p.situacao}</StatusBadge>}
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">
                    {formatBRL(p.valor_total)}
                  </p>
                  <p className="text-xs text-gray-500">
                    {formatDate(p.data_atualizacao_fonte)}
                  </p>
                </div>
              </div>

              <p className="mt-2 text-sm text-gray-800 dark:text-gray-200">
                {p.titulo ?? p.objeto ?? "—"}
              </p>

              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
                <span>
                  {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                  {p.uf ? `/${p.uf}` : ""}
                </span>
                <button
                  onClick={() => baixarPdfProposta(p.id)}
                  className="underline"
                >
                  PDF
                </button>
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
