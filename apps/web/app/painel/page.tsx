"use client";

import {
  ArrowUpRight,
  Compass,
  HandCoins,
  HardHat,
  LayoutDashboard,
  ShieldCheck,
  Target,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonCards } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  href: string;
}
interface Municipio {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
}
interface VisaoGeral {
  papel?: string | null;
  municipios: Municipio[];
  areas: string[];
  dimensoes: Dimensao[];
}

// Identidade visual de cada etapa do ciclo do recurso público.
interface DimensaoVisual {
  icon: LucideIcon;
  chip: string;
}
const VISUAL_PADRAO: DimensaoVisual = {
  icon: Target,
  chip: "bg-brand-50 text-brand-700 ring-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:ring-brand-900/50",
};
const DIMENSAO_VISUAL: Record<string, DimensaoVisual> = {
  captacao: VISUAL_PADRAO,
  recebidos: {
    icon: HandCoins,
    chip: "bg-green-50 text-green-700 ring-green-100 dark:bg-green-900/30 dark:text-green-300 dark:ring-green-900/50",
  },
  conformidade: {
    icon: ShieldCheck,
    chip: "bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-900/50",
  },
  obras: {
    icon: HardHat,
    chip: "bg-purple-50 text-purple-700 ring-purple-100 dark:bg-purple-900/30 dark:text-purple-300 dark:ring-purple-900/50",
  },
};

export default function MeuPainelPage() {
  const [data, setData] = useState<VisaoGeral | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      const { data: d } = await api.GET("/api/v1/perfil/visao-geral");
      if (d) setData(d as VisaoGeral);
      setLoading(false);
    })();
  }, []);

  const semTerritorio = !loading && (data?.municipios.length ?? 0) === 0;

  return (
    <>
      <PageHeader
        icon={LayoutDashboard}
        title="Meu painel"
        subtitle="Tudo do seu território, por etapa do ciclo do recurso público."
      />

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <EmptyState
          icon={Compass}
          title="Você ainda não acompanha nenhum município"
          description="O Hub Capture se organiza a partir do seu perfil — comece escolhendo os municípios e áreas que quer acompanhar."
          action={
            <Link href="/onboarding">
              <Button icon={<Compass className="h-4 w-4" aria-hidden />}>
                Configurar meu perfil
              </Button>
            </Link>
          }
        />
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 stagger">
          {(data?.dimensoes ?? []).map((d) => {
            const visual = DIMENSAO_VISUAL[d.chave] ?? VISUAL_PADRAO;
            const Icon = visual.icon;
            return (
              <Link
                key={d.chave}
                href={d.href}
                className="group rounded-2xl border border-gray-200 bg-white p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-700"
              >
                <div className="flex items-start justify-between gap-3">
                  <span
                    className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ring-1 transition-transform duration-200 group-hover:scale-110 ${visual.chip}`}
                  >
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="text-3xl font-bold tabular-nums tracking-tight">
                    {d.total}
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-between gap-2">
                  <div>
                    <h2 className="font-semibold transition-colors group-hover:text-brand-700 dark:group-hover:text-brand-300">
                      {d.titulo}
                    </h2>
                    <p className="mt-0.5 text-sm text-gray-500">{d.destaque ?? "—"}</p>
                  </div>
                  <ArrowUpRight
                    className="h-4 w-4 shrink-0 text-gray-300 transition-all duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-brand-600 dark:text-gray-600"
                    aria-hidden
                  />
                </div>
              </Link>
            );
          })}
        </section>
      )}
    </>
  );
}
