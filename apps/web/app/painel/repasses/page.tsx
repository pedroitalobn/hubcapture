"use client";

import { Banknote, HandCoins, Layers } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Callout } from "@/components/Callout";
import { DateRangePresets, presetToInicio, type RangePreset } from "@/components/DateRangePresets";
import { Feed } from "@/components/Feed";
import { FilterChips } from "@/components/FilterChips";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { SyncMunicipioForm } from "@/components/SyncMunicipioForm";
import { api } from "@/lib/api/client";
import { formatBRL } from "@/lib/format";

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
  const [ok, setOk] = useState<string | null>(null);
  const [sincronizando, setSincronizando] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    const { data: vg, error } = await api.GET("/api/v1/repasses/visao-geral", {
      params: { query: { inicio: presetToInicio(preset) } },
    });
    if (error) {
      setErro("Falha ao carregar a visão geral.");
    } else {
      setData(vg as VisaoGeral);
    }
    setLoading(false);
  }, [preset]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function sincronizar(ibge: string) {
    setErro(null);
    setOk(null);
    setSincronizando(true);
    const { error } = await api.POST("/api/v1/repasses/sync", {
      body: { municipio_ibge: ibge },
    });
    if (error) {
      setErro(
        "As fontes oficiais não responderam agora (comum: instabilidade/rede). Tente novamente.",
      );
    } else {
      setOk("Sincronização concluída.");
      await carregar();
    }
    setSincronizando(false);
  }

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

  return (
    <>
      <PageHeader
        icon={HandCoins}
        title="Recursos recebidos"
        subtitle="Repasses que entraram no caixa do seu território."
        actions={<DateRangePresets value={preset} onChange={setPreset} />}
      />

      <SyncMunicipioForm onSync={sincronizar} loading={sincronizando} />

      {erro && <Callout tone="error">{erro}</Callout>}
      {ok && <Callout tone="success">{ok}</Callout>}

      {loading ? (
        <SkeletonCards />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 stagger">
            <StatCard
              label="Total Pago"
              value={formatBRL(data?.total_pago)}
              context={`${data?.movimentacoes ?? 0} movimentações`}
              icon={Banknote}
              tone="success"
            />
            <StatCard
              label="Fontes"
              value={String(data?.fontes.length ?? 0)}
              context="com movimentação no período"
              icon={Layers}
              tone="brand"
            />
          </div>

          {chips.length > 0 && (
            <FilterChips options={chips} selected={fonteSel} onSelect={setFonteSel} />
          )}

          <section>
            <Feed dias={feed} />
          </section>
        </>
      )}
    </>
  );
}
