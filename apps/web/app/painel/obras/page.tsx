"use client";

import {
  Activity,
  BadgeCheck,
  Building2,
  HardHat,
  MapPin,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { ProgressBar, type ProgressTone } from "@/components/ProgressBar";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SyncMunicipioForm } from "@/components/SyncMunicipioForm";
import { api } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

interface Obra {
  id: string;
  fonte: string;
  nome?: string | null;
  objeto?: string | null;
  eixo?: string | null;
  situacao?: string | null;
  percentual_execucao?: string | null;
  valor_investimento?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  municipio_nome?: string | null;
  municipio_ibge?: string | null;
}
interface SituacaoResumo {
  situacao: string;
  total: number;
  valor_investimento: string;
}
interface Resumo {
  total: number;
  em_execucao: number;
  concluidas: number;
  paralisadas: number;
  valor_investimento_total: string;
  valor_repassado_total: string;
  por_situacao: SituacaoResumo[];
  obras: Obra[];
}

const SIT_TONE: Record<string, BadgeTone> = {
  planejada: "info",
  em_execucao: "warning",
  concluida: "success",
  paralisada: "danger",
  cancelada: "neutral",
};
const SIT_PROGRESS: Record<string, ProgressTone> = {
  planejada: "brand",
  em_execucao: "warning",
  concluida: "success",
  paralisada: "danger",
  cancelada: "brand",
};
const SIT_LABEL: Record<string, string> = {
  planejada: "Planejada",
  em_execucao: "Em execução",
  concluida: "Concluída",
  paralisada: "Paralisada",
  cancelada: "Cancelada",
};
const FONTE_LABEL: Record<string, string> = {
  sismob: "SISMOB · Saúde",
  simec: "SIMEC · Educação",
  caixa: "CAIXA · Infra",
};

/** Mini-mapa offline: dispersa as obras por lat/long num plano relativo.
 * Não usa tiles externos (funciona sem rede); em produção pode virar Leaflet. */
function MiniMapa({ obras }: { obras: Obra[] }) {
  const geo = obras.filter((o) => o.latitude && o.longitude);
  if (geo.length === 0) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-gray-300 text-sm text-gray-500 dark:border-gray-700">
        <MapPin className="h-6 w-6 text-gray-300 dark:text-gray-600" aria-hidden />
        Sem coordenadas para plotar no mapa.
      </div>
    );
  }
  const lats = geo.map((o) => Number(o.latitude));
  const lons = geo.map((o) => Number(o.longitude));
  const [minLa, maxLa] = [Math.min(...lats), Math.max(...lats)];
  const [minLo, maxLo] = [Math.min(...lons), Math.max(...lons)];
  const spanLa = maxLa - minLa || 1;
  const spanLo = maxLo - minLo || 1;
  return (
    <div className="relative h-64 overflow-hidden rounded-xl border border-gray-200 bg-[radial-gradient(circle_at_1px_1px,rgb(148_163_184/0.25)_1px,transparent_0)] bg-[size:16px_16px] bg-gray-50 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900">
      {geo.map((o) => {
        const x = ((Number(o.longitude) - minLo) / spanLo) * 92 + 4;
        const y = 96 - ((Number(o.latitude) - minLa) / spanLa) * 92;
        const tone = SIT_TONE[o.situacao ?? ""] ?? "neutral";
        const dot: Record<string, string> = {
          info: "bg-blue-500",
          warning: "bg-amber-500",
          success: "bg-green-500",
          danger: "bg-red-500",
          neutral: "bg-gray-400",
        };
        return (
          <span
            key={o.id}
            title={`${o.nome ?? o.objeto ?? "Obra"} — ${SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? ""}`}
            className={`absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full ring-2 ring-white transition-transform duration-150 hover:scale-150 dark:ring-gray-900 ${dot[tone]} ${o.situacao === "em_execucao" ? "animate-pulse-dot" : ""}`}
            style={{ left: `${x}%`, top: `${y}%` }}
          />
        );
      })}
    </div>
  );
}

export default function ObrasPage() {
  const [data, setData] = useState<Resumo | null>(null);
  const [loading, setLoading] = useState(true);
  const [sit, setSit] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [sinc, setSinc] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    const { data: d, error } = await api.GET("/api/v1/obras/resumo", {
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
    const { data: r, error } = await api.POST("/api/v1/obras/sync", {
      body: { municipio_ibge: ibge },
    });
    const gravados = (r as { gravados?: number } | undefined)?.gravados ?? 0;
    if (error) {
      setErro("As fontes de obras não responderam agora. Tente novamente.");
    } else if (gravados > 0) {
      setOk(`Sincronização concluída (${gravados} obras).`);
    } else {
      setErro("Nenhuma obra retornada pelas fontes (podem estar indisponíveis).");
    }
    if (!error) await carregar();
    setSinc(false);
  }

  const obras = useMemo(() => {
    const all = data?.obras ?? [];
    return sit ? all.filter((o) => o.situacao === sit) : all;
  }, [data, sit]);

  const chips = (data?.por_situacao ?? []).map((s) => ({
    value: s.situacao,
    label: SIT_LABEL[s.situacao] ?? s.situacao,
    count: s.total,
  }));

  return (
    <>
      <PageHeader
        icon={HardHat}
        title="Obras"
        subtitle="Execução no seu território (SISMOB · SIMEC · CAIXA)."
      />

      <SyncMunicipioForm onSync={sincronizar} loading={sinc} />

      {erro && <Callout tone="error">{erro}</Callout>}
      {ok && <Callout tone="success">{ok}</Callout>}

      {loading ? (
        <SkeletonCards />
      ) : (data?.total ?? 0) === 0 ? (
        <EmptyState
          icon={Building2}
          title="Sem obras no cache ainda"
          description="Sincronize um município acima para trazer as obras das fontes de execução."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 stagger">
            <StatCard
              label="Obras"
              value={String(data?.total ?? 0)}
              icon={Building2}
              tone="brand"
            />
            <StatCard
              label="Em execução"
              value={String(data?.em_execucao ?? 0)}
              icon={Activity}
              tone="warning"
            />
            <StatCard
              label="Concluídas"
              value={String(data?.concluidas ?? 0)}
              icon={BadgeCheck}
              tone="success"
            />
            <StatCard
              label="Investimento"
              value={formatBRL(data?.valor_investimento_total)}
              context={`repassado ${formatBRL(data?.valor_repassado_total)}`}
              icon={Wallet}
              tone="neutral"
            />
          </div>

          <MiniMapa obras={obras} />

          {chips.length > 0 && (
            <FilterChips options={chips} selected={sit} onSelect={setSit} />
          )}

          <ul className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900">
            {obras.map((o) => {
              const pct = o.percentual_execucao
                ? Number(o.percentual_execucao)
                : null;
              return (
                <li
                  key={o.id}
                  className="border-b border-gray-100 px-4 py-3 text-sm transition-colors last:border-b-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">
                        {o.nome ?? o.objeto ?? "Obra"}
                      </span>
                      <span className="text-xs text-gray-400">
                        {FONTE_LABEL[o.fonte] ?? o.fonte}
                        {o.valor_investimento
                          ? ` · ${formatBRL(o.valor_investimento)}`
                          : ""}
                      </span>
                    </span>
                    <StatusBadge
                      tone={SIT_TONE[o.situacao ?? ""] ?? "neutral"}
                      pulse={o.situacao === "em_execucao"}
                    >
                      {SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? "—"}
                    </StatusBadge>
                  </div>
                  {pct !== null && !Number.isNaN(pct) && (
                    <div className="mt-2 flex items-center gap-2">
                      <ProgressBar
                        value={pct}
                        tone={SIT_PROGRESS[o.situacao ?? ""] ?? "brand"}
                        className="flex-1"
                      />
                      <span className="shrink-0 text-xs font-medium tabular-nums text-gray-500">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </>
  );
}
