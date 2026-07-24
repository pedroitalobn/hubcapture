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
        <h1 className="page-title">Captação</h1>
        <p className="mt-1 text-sm text-ink-2">
          Propostas e editais abertos para o seu território.
        </p>
      </header>

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
        {propostas.length === 0 ? (
          <p className="text-ink-3">
            Nenhuma proposta no cache ainda. Faça uma consulta avulsa acima.
          </p>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-hairline text-left label-mono">
                  <th className="px-5 py-3">Nº</th>
                  <th className="px-3 py-3">Título</th>
                  <th className="px-3 py-3">Município</th>
                  <th className="px-3 py-3">Valor</th>
                  <th className="px-3 py-3">Situação</th>
                  <th className="px-3 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {propostas.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-hairline last:border-0 hover:bg-surface-2"
                  >
                    <td className="px-5 py-3 font-mono text-xs text-ink-2">
                      {p.id_externo}
                    </td>
                    <td className="px-3 py-3">{p.titulo ?? "—"}</td>
                    <td className="px-3 py-3 text-ink-2">
                      {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                      {p.uf ? `/${p.uf}` : ""}
                    </td>
                    <td className="px-3 py-3 tabular-nums">
                      {formatBRL(p.valor_total)}
                    </td>
                    <td className="px-3 py-3 text-ink-2">{p.situacao ?? "—"}</td>
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
