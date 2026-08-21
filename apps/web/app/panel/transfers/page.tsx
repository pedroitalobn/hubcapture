"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DateRangePresets, presetToInicio, type RangePreset } from "@/components/DateRangePresets";
import { Feed } from "@/components/Feed";
import { PageHeader } from "@/components/PageHeader";
import { IconeAcao } from "@/components/icons";
import { SkeletonCards } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api/client";
import { formatBRL, formatBRLCompact } from "@/lib/format";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";
import { paramFonte, useOrigem } from "@/lib/origem";

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

export default function RepassesPage() {
  const { selecionados } = useTerritorio();
  const [preset, setPreset] = useState<RangePreset>("30d");
  const [data, setData] = useState<VisaoGeral | null>(null);
  const [loading, setLoading] = useState(true);
  // origem do recurso vem do TRILHO (multi-select global) — a página não tem
  // mais chip próprio de fonte; um filtro em dois lugares dessincroniza.
  const { selecionadas: origens } = useOrigem();
  const [ibge, setIbge] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [sincronizando, setSincronizando] = useState(false);

  const carregar = useCallback(async () => {
    setLoading(true);
    const { data: vg, error } = await api.GET("/api/v1/transfers/overview", {
      params: {
        query: {
          inicio: presetToInicio(preset),
          municipio: paramMunicipio(selecionados),
          // a origem entra na CONSULTA, não numa peneira depois: filtrando só
          // o feed no cliente, o "Total Pago" e a contagem de movimentações
          // continuavam somando a fonte que o gestor tinha tirado da tela.
          fonte: paramFonte(origens),
        },
      },
    });
    if (error) {
      setMsg("Falha ao carregar a visão geral.");
    } else {
      setData(vg as VisaoGeral);
    }
    setLoading(false);
  }, [preset, selecionados, origens]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function sincronizar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSincronizando(true);
    const { error } = await api.POST("/api/v1/transfers/sync", {
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


  // a API já devolve o recorte da origem — a lista é a que veio
  const feed = data?.feed ?? [];

  return (
    <>
      <PageHeader
        titulo="Recursos recebidos"
        acoes={
          <>
            <Link
              href="/panel/transfers/amendments"
              className="btn btn-ghost btn-sm"
            >
              Emendas
              <IconeAcao nome="avancar" />
            </Link>
            <DateRangePresets value={preset} onChange={setPreset} />
          </>
        }
      />

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
            {/* BRL compacto no KPI: por extenso não cabe no card estreito e o
                .card corta o que estoura; o valor cheio fica no tooltip */}
            <StatCard
              label="Total Pago"
              value={formatBRLCompact(data?.total_pago)}
              title={formatBRL(data?.total_pago)}
              context={`${data?.movimentacoes ?? 0} movimentações`}
            />
            <StatCard
              label="Fontes"
              value={String(data?.fontes.length ?? 0)}
              context="com movimentação no período"
            />
          </div>

          <section>
            <Feed dias={feed} />
          </section>
        </>
      )}
    </>
  );
}
