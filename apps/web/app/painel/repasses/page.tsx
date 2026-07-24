"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { DateRangePresets, presetToInicio, type RangePreset } from "@/components/DateRangePresets";
import { Feed } from "@/components/Feed";
import { FilterChips } from "@/components/FilterChips";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
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
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [sincronizando, setSincronizando] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    const { data: vg, error } = await api.GET("/api/v1/repasses/visao-geral", {
      params: { query: { inicio: presetToInicio(preset) } },
    });
    if (error) {
      setMsg("Falha ao carregar a visão geral.");
    } else {
      setData(vg as VisaoGeral);
    }
    setLoading(false);
  }, [preset]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function sincronizar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSincronizando(true);
    const { error } = await api.POST("/api/v1/repasses/sync", {
      body: { municipio_ibge: ibge },
    });
    if (error) {
      setMsg(
        "As fontes oficiais não responderam agora (comum: instabilidade/rede). Tente novamente.",
      );
    } else {
      setMsg("Sincronização concluída.");
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
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">Recursos recebidos</h1>
        <DateRangePresets value={preset} onChange={setPreset} />
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
          disabled={sincronizando || ibge.length !== 7}
          className="btn btn-primary"
        >
          {sincronizando ? "Sincronizando…" : "Buscar nas fontes"}
        </button>
      </form>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      {loading ? (
        <SkeletonCards />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              label="Total Pago"
              value={formatBRL(data?.total_pago)}
              context={`${data?.movimentacoes ?? 0} movimentações`}
            />
            <StatCard
              label="Fontes"
              value={String(data?.fontes.length ?? 0)}
              context="com movimentação no período"
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
