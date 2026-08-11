"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatCard } from "@/components/StatCard";
import { SkeletonCards } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

interface Quebra {
  chave: string;
  rotulo: string;
  total: number;
  href: string;
}
interface Dimensao {
  chave: string;
  titulo: string;
  total: number;
  destaque?: string | null;
  href: string;
  quebras?: Quebra[];
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
        <h1 className="text-2xl font-bold">Meu painel</h1>
        <p className="text-sm text-gray-500">
          Tudo do seu território, por etapa do ciclo do recurso público.
        </p>
      </header>

      {loading ? (
        <SkeletonCards />
      ) : semTerritorio ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-6 text-sm dark:border-gray-700">
          <p className="mb-2 font-medium">Você ainda não acompanha nenhum município.</p>
          <p className="mb-3 text-gray-500">
            O Hub Capture se organiza a partir do seu perfil — comece escolhendo
            os municípios e áreas que quer acompanhar.
          </p>
          <Link
            href="/onboarding"
            className="inline-block rounded-md bg-brand px-4 py-2 text-brand-fg"
          >
            Configurar meu perfil
          </Link>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {(data?.dimensoes ?? []).map((d) => (
            <div
              key={d.chave}
              className="group rounded-xl border border-gray-200 p-5 transition hover:border-brand hover:shadow-sm dark:border-gray-800"
            >
              <Link href={d.href} className="block">
                <div className="flex items-baseline justify-between">
                  <h2 className="font-semibold group-hover:text-brand">{d.titulo}</h2>
                  <span className="text-2xl font-bold tabular-nums">{d.total}</span>
                </div>
                <p className="mt-1 text-sm text-gray-500">{d.destaque ?? "—"}</p>
              </Link>
              {/* recortes da dimensão (ex.: natureza jurídica) — já filtram a lista */}
              {(d.quebras ?? []).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {(d.quebras ?? []).map((q) => (
                    <Link
                      key={q.chave}
                      href={q.href}
                      className="inline-flex items-center gap-1.5 rounded-full border border-gray-300 px-3 py-1 text-xs text-gray-700 transition hover:border-brand hover:text-brand dark:border-gray-700 dark:text-gray-300"
                    >
                      {q.rotulo}
                      <span className="rounded-full bg-gray-200 px-1.5 tabular-nums dark:bg-gray-800">
                        {q.total}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>
      )}
    </>
  );
}
