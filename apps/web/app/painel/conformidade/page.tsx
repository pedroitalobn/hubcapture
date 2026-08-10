"use client";

import {
  BadgeCheck,
  CircleAlert,
  ClipboardCheck,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ProgressBar } from "@/components/ProgressBar";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SyncMunicipioForm } from "@/components/SyncMunicipioForm";
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
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
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

  async function sincronizar(ibge: string) {
    setErro(null);
    setOk(null);
    setSinc(true);
    const { error } = await api.POST("/api/v1/conformidade/sync", {
      body: { municipio_ibge: ibge },
    });
    if (error) setErro("A fonte (Tesouro) não respondeu agora. Tente novamente.");
    else {
      setOk("Sincronização concluída.");
      await carregar();
    }
    setSinc(false);
  }

  const requisitosPorSecao = (secao: string) =>
    (data?.requisitos ?? []).filter((r) => (r.secao ?? "—") === secao);

  return (
    <>
      <PageHeader
        icon={ShieldCheck}
        title="Conformidade fiscal"
        subtitle="Requisitos CAUC e capacidade de pagamento (CAPAG) do seu território."
      />

      <SyncMunicipioForm
        onSync={sincronizar}
        loading={sinc}
        buttonLabel="Buscar no Tesouro"
      />

      {erro && <Callout tone="error">{erro}</Callout>}
      {ok && <Callout tone="success">{ok}</Callout>}

      {loading ? (
        <SkeletonCards />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 stagger">
            <StatCard
              label="Requisitos"
              value={String(data?.total ?? 0)}
              icon={ClipboardCheck}
              tone="brand"
            />
            <StatCard
              label="Comprovados"
              value={String(data?.comprovados ?? 0)}
              icon={BadgeCheck}
              tone="success"
            />
            <StatCard
              label="A comprovar"
              value={String(data?.a_comprovar ?? 0)}
              icon={CircleAlert}
              tone="warning"
            />
            <StatCard
              label="CAPAG"
              value={data?.capag?.status ? "avaliado" : "—"}
              context="capacidade de pagamento"
              icon={Scale}
              tone="neutral"
            />
          </div>

          {(data?.secoes ?? []).map((sec) => {
            const pct = sec.total > 0 ? (sec.comprovados / sec.total) * 100 : 0;
            return (
              <section
                key={sec.secao}
                className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900"
              >
                <div className="border-b border-gray-100 bg-gray-50/70 px-4 py-3 dark:border-gray-800 dark:bg-gray-950/40">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
                      {sec.secao}
                    </h2>
                    <span className="text-xs font-medium tabular-nums text-gray-500">
                      {sec.comprovados}/{sec.total} comprovados
                    </span>
                  </div>
                  <ProgressBar
                    value={pct}
                    tone={pct >= 100 ? "success" : pct >= 50 ? "brand" : "warning"}
                    className="mt-2"
                  />
                </div>
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {requisitosPorSecao(sec.secao).map((r) => (
                    <li
                      key={r.id}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
                    >
                      <span className="min-w-0">
                        <span className="mr-1.5 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-500 dark:bg-gray-800">
                          {r.numero}
                        </span>
                        {r.descricao ?? "—"}
                        {r.orgao ? (
                          <span className="text-xs text-gray-400"> · {r.orgao}</span>
                        ) : null}
                      </span>
                      <StatusBadge
                        tone={TONE[r.status ?? ""] ?? "neutral"}
                        pulse={r.status === "a_comprovar"}
                      >
                        {LABEL[r.status ?? ""] ?? r.status ?? "—"}
                      </StatusBadge>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
          {(data?.total ?? 0) === 0 && (
            <EmptyState
              icon={ShieldCheck}
              title="Sem dados de conformidade"
              description="Sincronize um município acima para consultar os requisitos CAUC no Tesouro."
            />
          )}
        </>
      )}
    </>
  );
}
