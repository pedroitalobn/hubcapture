"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards, SkeletonLines } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { SyncForm } from "@/components/SyncForm";
import { Aviso, Card, cx } from "@/components/ui";
import { api } from "@/lib/api/client";
import { formatBRL, formatBRLCompact, formatDate } from "@/lib/format";

interface Obra {
  id: string;
  fonte: string;
  nome?: string | null;
  objeto?: string | null;
  eixo?: string | null;
  situacao?: string | null;
  percentual_execucao?: string | null;
  valor_investimento?: string | null;
  valor_repassado?: string | null;
  data_fim_prevista?: string | null;
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
const SIT_DOT: Record<BadgeTone, string> = {
  info: "bg-brand",
  warning: "bg-warn",
  success: "bg-ok",
  danger: "bg-danger",
  neutral: "bg-line-strong",
  brand: "bg-brand",
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
      <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface text-sm text-muted">
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
    <div className="relative h-64 overflow-hidden rounded-xl border border-line bg-surface">
      {geo.map((o) => {
        const x = ((Number(o.longitude) - minLo) / spanLo) * 92 + 4;
        const y = 96 - ((Number(o.latitude) - minLa) / spanLa) * 92;
        const tone = SIT_TONE[o.situacao ?? ""] ?? "neutral";
        return (
          <span
            key={o.id}
            title={`${o.nome ?? o.objeto ?? "Obra"} — ${SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? ""}`}
            className={cx(
              "absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-bg",
              SIT_DOT[tone],
            )}
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
  const [ibgeSugerido, setIbgeSugerido] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    const { data: d, error } = await api.GET("/api/v1/obras/resumo", {
      params: { query: {} },
    });
    if (error) setErro("Não foi possível carregar o resumo de obras.");
    else setData(d as Resumo);
    setLoading(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    void (async () => {
      const { data: perfil } = await api.GET("/api/v1/perfil");
      const m = (perfil as { municipios?: { ibge: string }[] } | undefined)?.municipios?.[0];
      if (m) setIbgeSugerido(m.ibge);
    })();
  }, []);

  const obras = useMemo(() => {
    const all = data?.obras ?? [];
    return sit ? all.filter((o) => o.situacao === sit) : all;
  }, [data, sit]);

  const chips = (data?.por_situacao ?? []).map((s) => ({
    value: s.situacao,
    label: SIT_LABEL[s.situacao] ?? s.situacao,
    count: s.total,
  }));

  const pctRepassado =
    Number(data?.valor_investimento_total) > 0
      ? (Number(data!.valor_repassado_total) / Number(data!.valor_investimento_total)) * 100
      : null;

  return (
    <>
      <PageHeader
        titulo="Obras"
        descricao="Execução no seu território (SISMOB · SIMEC · CAIXA)."
      />

      <SyncForm
        rotulo="Sincronizar município (IBGE)"
        botao="Buscar nas fontes"
        erroPadrao="As fontes de obras não responderam agora. Tente novamente."
        ibgeSugerido={ibgeSugerido}
        onSync={async (ibge) => {
          const { data: r, error } = await api.POST("/api/v1/obras/sync", {
            body: { municipio_ibge: ibge },
          });
          if (error) return { ok: false };
          const gravados = (r as { gravados?: number } | undefined)?.gravados ?? 0;
          await carregar();
          return {
            ok: true,
            mensagem:
              gravados > 0
                ? `Sincronização concluída (${gravados} obras).`
                : "Nenhuma obra retornada pelas fontes (podem estar indisponíveis).",
          };
        }}
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {loading ? (
        <>
          <SkeletonCards />
          <SkeletonLines count={4} />
        </>
      ) : (data?.total ?? 0) === 0 ? (
        <EmptyState
          titulo="Sem obras no cache ainda."
          descricao="Sincronize um município acima para buscar em SISMOB, SIMEC e CAIXA."
        />
      ) : (
        <>
          <StatRow cols={4}>
            <StatCard
              label="Obras"
              value={String(data?.total ?? 0)}
              context={`${data?.concluidas ?? 0} concluídas`}
            />
            <StatCard
              label="Em execução"
              value={String(data?.em_execucao ?? 0)}
              context="andamento em curso"
            />
            <StatCard
              label="Paralisadas"
              value={String(data?.paralisadas ?? 0)}
              tone={(data?.paralisadas ?? 0) > 0 ? "alerta" : "ok"}
              context={(data?.paralisadas ?? 0) > 0 ? "exigem atenção" : "nenhuma parada"}
            />
            <StatCard
              label="Investimento"
              value={formatBRLCompact(data?.valor_investimento_total)}
              title={formatBRL(data?.valor_investimento_total)}
              context={
                pctRepassado !== null
                  ? `${pctRepassado.toFixed(0)}% já repassado`
                  : `repassado ${formatBRLCompact(data?.valor_repassado_total)}`
              }
            />
          </StatRow>

          <MiniMapa obras={obras} />

          {chips.length > 0 && (
            <FilterChips
              ariaLabel="Filtrar por situação"
              options={chips}
              selected={sit}
              onSelect={setSit}
              todasLabel="Todas as situações"
              todasCount={data?.total}
            />
          )}

          {obras.length === 0 ? (
            <EmptyState titulo="Nenhuma obra com esse filtro." />
          ) : (
            <Card>
              <ul className="flex flex-col divide-y divide-line">
                {obras.map((o) => {
                  const pct = o.percentual_execucao ? Number(o.percentual_execucao) : null;
                  return (
                    <li key={o.id} className="flex flex-col gap-2 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="min-w-0 text-sm font-medium text-ink">
                          {o.nome ?? o.objeto ?? "Obra"}
                        </span>
                        <StatusBadge tone={SIT_TONE[o.situacao ?? ""] ?? "neutral"}>
                          {SIT_LABEL[o.situacao ?? ""] ?? o.situacao ?? "—"}
                        </StatusBadge>
                      </div>

                      {pct !== null && Number.isFinite(pct) && (
                        <div className="flex items-center gap-2">
                          <div
                            className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2"
                            role="progressbar"
                            aria-valuenow={Math.round(pct)}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label="Percentual executado"
                          >
                            <div
                              className={cx(
                                "h-full rounded-full",
                                o.situacao === "paralisada" ? "bg-danger" : "bg-brand",
                              )}
                              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                            />
                          </div>
                          <span className="num shrink-0 text-xs font-medium text-ink-2">
                            {pct.toFixed(0)}%
                          </span>
                        </div>
                      )}

                      <p className="num text-xs text-muted">
                        {FONTE_LABEL[o.fonte] ?? o.fonte}
                        {o.valor_investimento && ` · ${formatBRL(o.valor_investimento)}`}
                        {o.valor_repassado &&
                          ` · repassado ${formatBRL(o.valor_repassado)}`}
                        {o.data_fim_prevista &&
                          ` · previsão ${formatDate(o.data_fim_prevista)}`}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </>
      )}
    </>
  );
}
