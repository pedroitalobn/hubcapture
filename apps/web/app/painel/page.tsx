"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BuscaPropostas } from "@/components/BuscaPropostas";
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
        <>
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {(data?.dimensoes ?? []).map((d) => (
              <Link
                key={d.chave}
                href={d.href}
                className="group rounded-xl border border-gray-200 p-5 transition hover:border-brand hover:shadow-sm dark:border-gray-800"
              >
                <div className="flex items-baseline justify-between">
                  <h2 className="font-semibold group-hover:text-brand">{d.titulo}</h2>
                  <span className="text-2xl font-bold tabular-nums">{d.total}</span>
                </div>
                <p className="mt-1 text-sm text-gray-500">{d.destaque ?? "—"}</p>
              </Link>
            ))}
          </section>

          {/* Busca de propostas direto no painel — sobre o cache do território */}
          <section className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-semibold">Buscar propostas</h2>
              <p className="text-sm text-gray-500">
                Por número, município, natureza jurídica e faixa de valor.
              </p>
            </div>
            <BuscaPropostas />
          </section>
        </>
      )}
    </>
  );
}
