"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
      <header>
        <h1 className="text-display text-3xl">Meu painel</h1>
        <p className="mt-1 text-sm text-ink-2">
          Tudo do seu território, por etapa do ciclo do recurso público.
        </p>
      </header>

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <div className="card p-8 text-sm">
          <p className="mb-2 text-base font-semibold tracking-tight">
            Você ainda não acompanha nenhum município.
          </p>
          <p className="mb-5 max-w-md leading-relaxed text-ink-2">
            O Hub Capture se organiza a partir do seu perfil — comece escolhendo
            os municípios e áreas que quer acompanhar.
          </p>
          <Link href="/onboarding" className="btn btn-primary">
            Configurar meu perfil
          </Link>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(data?.dimensoes ?? []).map((d) => (
            <Link key={d.chave} href={d.href} className="card card-hover group p-6">
              <div className="flex items-baseline justify-between">
                <h2 className="font-semibold tracking-tight">{d.titulo}</h2>
                <span className="text-display text-3xl tabular-nums">{d.total}</span>
              </div>
              <p className="mt-2 text-sm text-ink-2">{d.destaque ?? "—"}</p>
              <p className="mt-4 text-xs font-medium text-brand-deep opacity-0 transition-opacity group-hover:opacity-100 dark:text-brand">
                Abrir →
              </p>
            </Link>
          ))}
        </section>
      )}
    </>
  );
}
