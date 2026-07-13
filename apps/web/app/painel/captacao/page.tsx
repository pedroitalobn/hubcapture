"use client";

import { useCallback, useEffect, useState } from "react";
import { api, baixarPdfProposta } from "@/lib/api/client";

type Proposta = {
  id: string;
  id_externo: string;
  titulo?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
  fonte: string;
};

function formatBRL(v?: string | null): string {
  if (!v) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function CaptacaoPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/propostas", {
      params: { query: {} },
    });
    if (error) {
      setMsg("Falha ao carregar propostas.");
      return;
    }
    setPropostas((data as Proposta[]) ?? []);
  }, []);

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

  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">Captação</h1>
        <p className="text-sm text-gray-500">
          Propostas e editais abertos para o seu território.
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

      <section className="overflow-x-auto">
        {propostas.length === 0 ? (
          <p className="text-gray-500">
            Nenhuma proposta no cache ainda. Faça uma consulta avulsa acima.
          </p>
        ) : (
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
              {propostas.map((p) => (
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
        )}
      </section>
    </>
  );
}
