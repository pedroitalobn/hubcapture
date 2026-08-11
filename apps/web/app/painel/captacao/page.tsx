"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PropostasTable, type Proposta } from "@/components/BuscaPropostas";
import { api } from "@/lib/api/client";

/**
 * Lente de Captação: a lista do território + a consulta avulsa (o único fetch
 * ao vivo na fonte). A busca com filtros mora em `/painel`.
 */
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
          Propostas e editais abertos para o seu território. Para buscar por
          número, município, natureza jurídica ou valor, use a{" "}
          <Link href="/painel" className="text-brand underline">
            busca do painel
          </Link>
          .
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
          <PropostasTable propostas={propostas} />
        )}
      </section>
    </>
  );
}
