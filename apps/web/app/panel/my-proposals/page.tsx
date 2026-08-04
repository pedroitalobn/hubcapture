"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";

type Proposta = {
  id: string;
  fonte: string;
  id_externo: string;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_nome?: string | null;
  municipio_ibge?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
};

function brl(v?: string | null): string {
  const n = Number(v);
  if (!v || Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function MinhasPropostasPage() {
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { data } = await api.GET("/api/v1/favorites/proposals");
    if (data) setPropostas(data as Proposta[]);
    setCarregando(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function desfavoritar(id: string) {
    await api.DELETE("/api/v1/favorites/{proposta_id}", {
      params: { path: { proposta_id: id } },
    });
    setPropostas((prev) => prev.filter((p) => p.id !== id));
  }

  return (
    <>
      <header>
        <h1 className="page-title">Minhas Propostas</h1>
        <p className="mt-1 text-sm text-ink-2">
          As propostas que você favoritou para acompanhar. Clique para ver todos os
          dados; a estrela remove daqui.
        </p>
      </header>

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : propostas.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-ink-2">
            Você ainda não favoritou nenhuma proposta.
          </p>
          <Link href="/panel/funding" className="btn btn-primary mt-4 inline-flex">
            Ir para a Captação
          </Link>
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-3">
                <th className="w-10 px-4 py-3" />
                <th className="px-3 py-3">Proposta</th>
                <th className="px-3 py-3">Município</th>
                <th className="px-3 py-3">Valor</th>
                <th className="px-3 py-3">Situação</th>
              </tr>
            </thead>
            <tbody>
              {propostas.map((p) => (
                <tr key={p.id} className="border-b border-hairline last:border-0 hover:bg-surface-2">
                  <td className="px-4 py-3">
                    <button
                      onClick={() => void desfavoritar(p.id)}
                      aria-label="Desfavoritar"
                      title="Remover das minhas propostas"
                      className="text-amber-500"
                    >
                      ★
                    </button>
                  </td>
                  <td className="px-3 py-3">
                    <Link href={`/panel/funding/${p.id}`} className="font-medium hover:underline">
                      {p.titulo ?? p.objeto ?? p.id_externo}
                    </Link>
                    <p className="mt-0.5 max-w-md text-xs text-ink-3">
                      {[p.orgao_superior, p.modalidade, p.id_externo].filter(Boolean).join(" · ")}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-ink-2">
                    {p.municipio_nome ?? p.municipio_ibge ?? "—"}
                    {p.uf ? `/${p.uf}` : ""}
                  </td>
                  <td className="px-3 py-3 tabular-nums">{brl(p.valor_total)}</td>
                  <td className="px-3 py-3 text-ink-2">{p.situacao ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
