"use client";

import { useCallback, useEffect, useState } from "react";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SkeletonCards } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

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
    void carregar();
  }, [carregar]);

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
    <>
      <header>
        <h1 className="text-display text-3xl">Conformidade fiscal</h1>
        <p className="mt-1 text-sm text-ink-2">CAUC e CAPAG do seu território.</p>
      </header>

      <form onSubmit={sincronizar} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Sincronizar município (IBGE)</span>
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
          disabled={sinc || ibge.length !== 7}
          className="btn btn-primary"
        >
          {sinc ? "Sincronizando…" : "Buscar no Tesouro"}
        </button>
      </form>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

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
            <section key={sec.secao} className="card flex flex-col gap-2 p-5">
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                {sec.secao} · {sec.comprovados}/{sec.total} comprovados
              </h2>
              <ul className="flex flex-col divide-y divide-hairline">
                {requisitosPorSecao(sec.secao).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span className="text-ink-2">
                      <span className="font-mono text-xs text-ink-3">{r.numero}</span>{" "}
                      <span className="text-ink">{r.descricao ?? "—"}</span>
                      {r.orgao ? (
                        <span className="text-xs text-ink-3"> · {r.orgao}</span>
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
            <p className="text-ink-3">
              Sem dados de conformidade. Sincronize um município acima.
            </p>
          )}
        </>
      )}
    </>
  );
}
