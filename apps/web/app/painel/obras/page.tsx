"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FilterChips } from "@/components/FilterChips";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
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
      <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-hairline text-sm text-ink-3">
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
    <div className="card relative h-64 overflow-hidden bg-surface-2">
      {geo.map((o) => {
        const x = ((Number(o.longitude) - minLo) / spanLo) * 92 + 4;
        const y = 96 - ((Number(o.latitude) - minLa) / spanLa) * 92;
        const tone = SIT_TONE[o.situacao ?? ""] ?? "neutral";
        const dot: Record<string, string> = {
          info: "bg-blue-500",
          warning: "bg-brand",
          success: "bg-green-500",
          danger: "bg-red-500",
          neutral: "bg-ink-3",
        };
        return (
          <span
            key={o.id}
            title={`${o.nome ?? o.objeto ?? "Obra"} — ${SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? ""}`}
            className={`absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full shadow-md ring-2 ring-surface ${dot[tone]}`}
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
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
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

  async function sincronizar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSinc(true);
    const { data: r, error } = await api.POST("/api/v1/obras/sync", {
      body: { municipio_ibge: ibge },
    });
    const gravados = (r as { gravados?: number } | undefined)?.gravados ?? 0;
    setMsg(
      error
        ? "As fontes de obras não responderam agora. Tente novamente."
        : gravados > 0
          ? `Sincronização concluída (${gravados} obras).`
          : "Nenhuma obra retornada pelas fontes (podem estar indisponíveis).",
    );
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
      <header>
        <h1 className="text-display text-3xl">Obras</h1>
        <p className="mt-1 text-sm text-ink-2">
          Execução no seu território (SISMOB · SIMEC · CAIXA).
        </p>
      </header>

      <form onSubmit={sincronizar} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Sincronizar município (IBGE, 7 dígitos)</span>
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
          {sinc ? "Sincronizando…" : "Buscar nas fontes"}
        </button>
      </form>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {loading ? (
        <SkeletonCards />
      ) : (data?.total ?? 0) === 0 ? (
        <p className="text-ink-3">
          Sem obras no cache ainda. Sincronize um município acima.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Obras" value={String(data?.total ?? 0)} />
            <StatCard label="Em execução" value={String(data?.em_execucao ?? 0)} />
            <StatCard label="Concluídas" value={String(data?.concluidas ?? 0)} />
            <StatCard
              label="Investimento"
              value={formatBRL(data?.valor_investimento_total)}
              context={`repassado ${formatBRL(data?.valor_repassado_total)}`}
            />
          </div>

          <MiniMapa obras={obras} />

          {chips.length > 0 && (
            <FilterChips options={chips} selected={sit} onSelect={setSit} />
          )}

          <ul className="card flex flex-col divide-y divide-hairline px-5">
            {obras.map((o) => (
              <li key={o.id} className="flex items-start justify-between gap-3 py-3.5 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium tracking-tight">
                    {o.nome ?? o.objeto ?? "Obra"}
                  </span>
                  <span className="text-xs text-ink-3">
                    {FONTE_LABEL[o.fonte] ?? o.fonte}
                    {o.percentual_execucao
                      ? ` · ${Number(o.percentual_execucao).toFixed(0)}% executado`
                      : ""}
                    {o.valor_investimento
                      ? ` · ${formatBRL(o.valor_investimento)}`
                      : ""}
                  </span>
                </span>
                <StatusBadge tone={SIT_TONE[o.situacao ?? ""] ?? "neutral"}>
                  {SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? "—"}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
