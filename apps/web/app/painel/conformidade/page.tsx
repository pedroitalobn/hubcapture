"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SkeletonCards } from "@/components/Skeleton";
import { api, getToken } from "@/lib/api/client";

interface Requisito {
  id: string;
  numero: string;
  secao?: string | null;
  descricao?: string | null;
  status?: string | null;
  orgao?: string | null;
}
interface SecaoResumo {
  secao: string;
  total: number;
  comprovados: number;
  a_comprovar: number;
  desativados: number;
}
interface Resumo {
  total: number;
  comprovados: number;
  a_comprovar: number;
  desativados: number;
  secoes: SecaoResumo[];
  capag?: { status?: string | null } | null;
  requisitos: Requisito[];
}

const TONE: Record<string, BadgeTone> = {
  comprovado: "success",
  a_comprovar: "warning",
  desativado: "neutral",
};
const LABEL: Record<string, string> = {
  comprovado: "Comprovado",
  a_comprovar: "A comprovar",
  desativado: "Desativado",
};

export default function ConformidadePage() {
  const router = useRouter();
  const [data, setData] = useState<Resumo | null>(null);
  const [loading, setLoading] = useState(true);
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [sinc, setSinc] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    const { data: d, error } = await api.GET("/api/v1/conformidade", {
      params: { query: {} },
    });
    if (!error) setData(d as Resumo);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void carregar();
  }, [carregar, router]);

  async function sincronizar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSinc(true);
    const { error } = await api.POST("/api/v1/conformidade/sync", {
      body: { municipio_ibge: ibge },
    });
    setMsg(
      error
        ? "A fonte (Tesouro) não respondeu agora. Tente novamente."
        : "Sincronização concluída.",
    );
    if (!error) await carregar();
    setSinc(false);
  }

  const requisitosPorSecao = (secao: string) =>
    (data?.requisitos ?? []).filter((r) => (r.secao ?? "—") === secao);

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-8">
      <h1 className="text-2xl font-bold">Conformidade fiscal (CAUC/CAPAG)</h1>

      <form onSubmit={sincronizar} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Sincronizar município (IBGE)
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
          disabled={sinc || ibge.length !== 7}
          className="rounded-md bg-brand px-4 py-2 text-brand-fg disabled:opacity-60"
        >
          {sinc ? "Sincronizando…" : "Buscar no Tesouro"}
        </button>
      </form>
      {msg && <p className="text-sm text-gray-600 dark:text-gray-400">{msg}</p>}

      {loading ? (
        <SkeletonCards />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Requisitos" value={String(data?.total ?? 0)} />
            <StatCard label="Comprovados" value={String(data?.comprovados ?? 0)} />
            <StatCard label="A comprovar" value={String(data?.a_comprovar ?? 0)} />
            <StatCard
              label="CAPAG"
              value={data?.capag?.status ? "avaliado" : "—"}
              context="capacidade de pagamento"
            />
          </div>

          {(data?.secoes ?? []).map((sec) => (
            <section key={sec.secao} className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                {sec.secao} · {sec.comprovados}/{sec.total} comprovados
              </h2>
              <ul className="flex flex-col divide-y divide-gray-100 dark:divide-gray-900">
                {requisitosPorSecao(sec.secao).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span>
                      <span className="font-mono text-xs text-gray-500">{r.numero}</span>{" "}
                      {r.descricao ?? "—"}
                      {r.orgao ? (
                        <span className="text-xs text-gray-400"> · {r.orgao}</span>
                      ) : null}
                    </span>
                    <StatusBadge tone={TONE[r.status ?? ""] ?? "neutral"}>
                      {LABEL[r.status ?? ""] ?? r.status ?? "—"}
                    </StatusBadge>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {(data?.total ?? 0) === 0 && (
            <p className="text-gray-500">
              Sem dados de conformidade. Sincronize um município acima.
            </p>
          )}
        </>
      )}
    </main>
  );
}
