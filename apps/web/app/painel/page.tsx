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

// Acento visual por dimensão do ciclo (não por fonte — seção 19 do CLAUDE.md).
const ACENTO: Record<string, string> = {
  captacao: "from-indigo-400 to-sky-400",
  repasses: "from-emerald-400 to-teal-300",
  recebidos: "from-emerald-400 to-teal-300",
  conformidade: "from-amber-400 to-orange-300",
  obras: "from-fuchsia-400 to-violet-400",
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
      <header>
        <h1 className="text-gradient text-2xl font-bold">Meu painel</h1>
        <p className="text-sm text-gray-400">
          Tudo do seu território, por etapa do ciclo do recurso público.
        </p>
      </header>

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <div className="glass-card animate-fade-up p-8 text-sm">
          <p className="mb-2 text-base font-medium">
            Você ainda não acompanha nenhum município.
          </p>
          <p className="mb-4 text-gray-400">
            O Hub Capture se organiza a partir do seu perfil — comece escolhendo
            os municípios e áreas que quer acompanhar.
          </p>
          <Link href="/onboarding" className="btn-primary inline-flex px-5 py-2.5">
            Configurar meu perfil
          </Link>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(data?.dimensoes ?? []).map((d, i) => (
            <Link
              key={d.chave}
              href={d.href}
              className={`glass-card glass-hover animate-fade-up stagger-${(i % 6) + 1} group p-6`}
            >
              <div
                className={`mb-4 h-1 w-10 rounded-full bg-gradient-to-r ${
                  ACENTO[d.chave] ?? "from-indigo-400 to-sky-400"
                }`}
              />
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="font-semibold transition group-hover:text-white">
                  {d.titulo}
                </h2>
                <span className="text-gradient text-3xl font-bold tabular-nums">
                  {d.total}
                </span>
              </div>
              <p className="mt-1 text-sm text-gray-400">{d.destaque ?? "—"}</p>
              <span className="mt-3 inline-flex items-center gap-1 text-xs text-gray-500 transition group-hover:translate-x-0.5 group-hover:text-brand">
                Abrir
                <svg
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-3 w-3"
                >
                  <path d="M3 8h10M9 4l4 4-4 4" />
                </svg>
              </span>
            </Link>
          ))}
        </section>
      )}
    </>
  );
}
