"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearTokens, getToken } from "@/lib/api/client";

interface MunicipioPerfil {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
  modo: string;
}
interface Perfil {
  nome?: string | null;
  papel?: string | null;
  municipios: MunicipioPerfil[];
  areas: string[];
  modulos?: string[];
}

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
// Itens com `modulo` só aparecem se o módulo estiver ativo (painel admin).
const NAV = [
  { href: "/painel", label: "Meu painel", exact: true },
  { href: "/painel/captacao", label: "Captação", modulo: "captacao" },
  { href: "/painel/repasses", label: "Recursos recebidos", modulo: "recebidos" },
  {
    href: "/painel/conformidade",
    label: "Conformidade fiscal",
    modulo: "conformidade",
  },
  { href: "/painel/obras", label: "Obras", modulo: "obras" },
  { href: "/painel/chat", label: "Copiloto", modulo: "copiloto" },
  { href: "/painel/conta", label: "Minha conta" },
];

const PAPEL_LABEL: Record<string, string> = {
  parlamentar: "Parlamentar",
  executivo: "Executivo",
  equipe: "Equipe",
};

export default function PainelLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [perfil, setPerfil] = useState<Perfil | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const { data } = await api.GET("/api/v1/perfil");
      if (data) setPerfil(data as Perfil);
    })();
  }, [router]);

  function sair() {
    clearTokens();
    router.replace("/login");
  }

  const municipios = perfil?.municipios ?? [];
  const territorio =
    municipios.length === 0
      ? "Nenhum município — configure o onboarding"
      : municipios
          .map((m) => (m.nome ? `${m.nome}${m.uf ? `/${m.uf}` : ""}` : m.ibge))
          .join(" · ");

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-6 md:flex-row md:gap-8">
      <aside className="flex shrink-0 flex-col gap-6 md:w-64">
        <div>
          <Link href="/painel" className="text-lg font-bold">
            Hub Capture
          </Link>
          <p className="mt-1 text-xs uppercase tracking-wide text-gray-500">
            {perfil?.papel ? PAPEL_LABEL[perfil.papel] ?? perfil.papel : "Meu perfil"}
          </p>
        </div>

        {/* Território do perfil — a chave de tudo é o município, não a fonte. */}
        <div className="rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-800">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Território
          </p>
          <p className="text-gray-700 dark:text-gray-300">{territorio}</p>
          {(perfil?.areas ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {perfil!.areas.map((a) => (
                <span
                  key={a}
                  className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                >
                  {a}
                </span>
              ))}
            </div>
          )}
          <Link
            href="/onboarding"
            className="mt-2 inline-block text-xs text-brand underline"
          >
            Ajustar perfil
          </Link>
        </div>

        <nav className="flex flex-col gap-1 text-sm">
          {NAV.filter(
            (item) =>
              !item.modulo || (perfil?.modulos ?? []).includes(item.modulo)
          ).map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 ${
                  active
                    ? "bg-brand text-brand-fg"
                    : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={sair}
          className="mt-auto text-left text-xs text-gray-500 underline"
        >
          Sair
        </button>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col gap-6">{children}</main>
    </div>
  );
}
