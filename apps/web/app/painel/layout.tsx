"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
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
}

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
const NAV = [
  { href: "/painel", label: "Meu painel", exact: true },
  { href: "/painel/captacao", label: "Captação" },
  { href: "/painel/repasses", label: "Recursos recebidos" },
  { href: "/painel/conformidade", label: "Conformidade fiscal" },
  { href: "/painel/obras", label: "Obras" },
  { href: "/painel/chat", label: "Copiloto" },
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
    <div className="flex min-h-screen w-full flex-col gap-5 p-4 sm:p-6 md:flex-row md:gap-6 lg:p-8">
      <aside className="rail flex shrink-0 flex-col gap-6 self-start p-5 max-md:w-full md:sticky md:top-6 md:w-72 md:min-h-[calc(100vh-4rem)]">
        <div>
          <Link href="/painel">
            <BrandMark />
          </Link>
          <p className="label-mono mt-1.5">
            {perfil?.papel ? PAPEL_LABEL[perfil.papel] ?? perfil.papel : "Meu perfil"}
          </p>
        </div>

        {/* Território do perfil — a chave de tudo é o município, não a fonte. */}
        <div className="border-t border-hairline pt-4 text-sm">
          <p className="label-mono mb-1.5">Território</p>
          <p className="text-ink-2">{territorio}</p>
          {(perfil?.areas ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {perfil!.areas.map((a) => (
                <span
                  key={a}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 font-mono text-[11px] text-ink-2"
                >
                  <span className="brand-dot" aria-hidden />
                  {a}
                </span>
              ))}
            </div>
          )}
          <Link
            href="/onboarding"
            className="mt-3 inline-block font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
          >
            Ajustar perfil →
          </Link>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${active ? "nav-item-active" : ""}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={sair}
          className="mt-auto self-start font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 transition-colors hover:text-ink"
        >
          Sair da conta
        </button>
      </aside>

      <main className="mx-auto flex w-full min-w-0 max-w-[1600px] flex-1 flex-col gap-6 py-2">
        {children}
      </main>
    </div>
  );
}
