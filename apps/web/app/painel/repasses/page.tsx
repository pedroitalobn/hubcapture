"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DateRangePresets,
  presetToInicio,
  type RangePreset,
} from "@/components/DateRangePresets";
import { EmptyState } from "@/components/EmptyState";
import { Feed } from "@/components/Feed";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards, SkeletonLines } from "@/components/Skeleton";
import { StatCard, StatRow } from "@/components/StatCard";
import { SyncForm } from "@/components/SyncForm";
import { Aviso } from "@/components/ui";
import { api } from "@/lib/api/client";
import { formatBRL, formatBRLCompact, formatDate } from "@/lib/format";

interface FonteResumo {
  fonte: string;
  total: string;
  movimentacoes: number;
}
interface RepasseItem {
  id: string;
  fonte: string;
  descricao?: string | null;
  categoria?: string | null;
  natureza: string;
  valor?: string | null;
  emenda: boolean;
}
interface DiaGroup {
  data: string;
  subtotal: string;
  itens: RepasseItem[];
}
interface VisaoGeral {
  total_pago: string;
  movimentacoes: number;
  fontes: FonteResumo[];
  feed: DiaGroup[];
}

const FONTE_LABEL: Record<string, string> = {
  fpm: "FPM",
  emendas: "Emendas",
  fns: "FNS",
  fnde: "FNDE",
  transferegov_ff: "TransfereGov",
  caixa: "CAIXA",
};

export default function RepassesPage() {
  const [preset, setPreset] = useState<RangePreset>("30d");
  const [data, setData] = useState<VisaoGeral | null>(null);
  const [loading, setLoading] = useState(true);
  const [fonteSel, setFonteSel] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ibgeSugerido, setIbgeSugerido] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    const { data: vg, error } = await api.GET("/api/v1/repasses/visao-geral", {
      params: { query: { inicio: presetToInicio(preset) } },
    });
    if (error) setErro("Não foi possível carregar a visão geral de repasses.");
    else setData(vg as VisaoGeral);
    setLoading(false);
  }, [preset]);

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

  const chips = useMemo(
    () =>
      (data?.fontes ?? []).map((f) => ({
        value: f.fonte,
        label: FONTE_LABEL[f.fonte] ?? f.fonte,
        count: f.movimentacoes,
      })),
    [data],
  );

  const feed = useMemo(() => {
    const f = data?.feed ?? [];
    if (!fonteSel) return f;
    return f
      .map((d) => ({ ...d, itens: d.itens.filter((i) => i.fonte === fonteSel) }))
      .filter((d) => d.itens.length > 0);
  }, [data, fonteSel]);

  /** Métricas derivadas — completam a faixa de KPI, que ficava metade vazia. */
  const extras = useMemo(() => {
    const itens = (data?.feed ?? []).flatMap((d) => d.itens);
    let emendas = 0;
    let deducoes = 0;
    for (const i of itens) {
      const v = Number(i.valor);
      if (!Number.isFinite(v)) continue;
      if (i.emenda) emendas += v;
      if (i.natureza === "deducao") deducoes += v;
    }
    const maiorFonte = [...(data?.fontes ?? [])].sort(
      (a, b) => Number(b.total) - Number(a.total),
    )[0];
    const ultimoDia = data?.feed?.[0]?.data ?? null;
    return { emendas, deducoes, maiorFonte, ultimoDia };
  }, [data]);

  return (
    <>
      <PageHeader
        titulo="Recursos recebidos"
        descricao="O que já entrou no caixa do município, por fonte e por dia."
        acoes={<DateRangePresets value={preset} onChange={setPreset} />}
      />

      <SyncForm
        rotulo="Sincronizar município (IBGE)"
        botao="Buscar nas fontes"
        erroPadrao="As fontes oficiais não responderam agora (instabilidade ou rede). Tente novamente."
        ibgeSugerido={ibgeSugerido}
        onSync={async (ibge) => {
          const { error } = await api.POST("/api/v1/repasses/sync", {
            body: { municipio_ibge: ibge },
          });
          if (error) return { ok: false };
          await carregar();
          return { ok: true, mensagem: "Sincronização concluída e cache atualizado." };
        }}
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {loading ? (
        <>
          <SkeletonCards />
          <SkeletonLines count={5} />
        </>
      ) : (
        <>
          <StatRow cols={4}>
            <StatCard
              label="Total pago"
              value={formatBRLCompact(data?.total_pago)}
              title={formatBRL(data?.total_pago)}
              context={`${data?.movimentacoes ?? 0} movimentações no período`}
            />
            <StatCard
              label="Via emenda"
              value={formatBRLCompact(extras.emendas)}
              title={formatBRL(extras.emendas)}
              context={
                Number(data?.total_pago) > 0
                  ? `${((extras.emendas / Number(data!.total_pago)) * 100).toFixed(1)}% do total`
                  : "sem base de cálculo"
              }
            />
            <StatCard
              label="Deduções"
              value={formatBRLCompact(extras.deducoes)}
              title={formatBRL(extras.deducoes)}
              tone={extras.deducoes > 0 ? "alerta" : "neutral"}
              context="descontadas do bruto (FPM)"
            />
            <StatCard
              label="Maior fonte"
              value={
                extras.maiorFonte
                  ? (FONTE_LABEL[extras.maiorFonte.fonte] ?? extras.maiorFonte.fonte)
                  : "—"
              }
              context={
                extras.maiorFonte
                  ? formatBRLCompact(extras.maiorFonte.total)
                  : "nenhuma movimentação"
              }
            />
          </StatRow>

          {chips.length > 0 && (
            <FilterChips
              ariaLabel="Filtrar por fonte"
              options={chips}
              selected={fonteSel}
              onSelect={setFonteSel}
              todasLabel="Todas as fontes"
              todasCount={data?.movimentacoes}
            />
          )}

          {feed.length === 0 ? (
            <EmptyState
              titulo="Nenhum repasse no período."
              descricao="Amplie o intervalo acima ou sincronize um município para buscar nas fontes oficiais."
            />
          ) : (
            <section aria-label="Repasses por dia" className="flex flex-col gap-2">
              {extras.ultimoDia && (
                <p className="text-xs text-muted">
                  Movimentação mais recente em {formatDate(extras.ultimoDia)}.
                </p>
              )}
              <Feed dias={feed} />
            </section>
          )}
        </>
      )}
    </>
  );
}
