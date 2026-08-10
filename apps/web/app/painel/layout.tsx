"use client";

import {
  HandCoins,
  HardHat,
  Landmark,
  LayoutDashboard,
  LogOut,
  MapPin,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  UserRound,
  type LucideIcon,
} from "lucide-react";
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
}

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
const NAV: { href: string; label: string; icon: LucideIcon; exact?: boolean }[] = [
  { href: "/painel", label: "Meu painel", icon: LayoutDashboard, exact: true },
  { href: "/painel/captacao", label: "Captação", icon: Target },
  { href: "/painel/repasses", label: "Recursos recebidos", icon: HandCoins },
  { href: "/painel/conformidade", label: "Conformidade fiscal", icon: ShieldCheck },
  { href: "/painel/obras", label: "Obras", icon: HardHat },
  { href: "/painel/chat", label: "Copiloto", icon: Sparkles },
  { href: "/painel/conta", label: "Minha conta", icon: UserRound },
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
      <aside className="flex shrink-0 flex-col gap-5 md:sticky md:top-6 md:h-[calc(100vh-3rem)] md:w-64">
        <Link href="/painel" className="group flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-sm transition-transform duration-200 group-hover:scale-105">
            <Landmark className="h-4.5 w-4.5" aria-hidden />
          </span>
          <span>
            <span className="block text-base font-bold leading-tight tracking-tight">
              Hub Capture
            </span>
            <span className="block text-[11px] font-medium uppercase tracking-wider text-gray-500">
              {perfil?.papel
                ? PAPEL_LABEL[perfil.papel] ?? perfil.papel
                : "Meu perfil"}
            </span>
          </span>
        </Link>

        {/* Território do perfil — a chave de tudo é o município, não a fonte. */}
        <div className="rounded-xl border border-gray-200 bg-white p-3 text-sm shadow-card dark:border-gray-800 dark:bg-gray-900">
          <p className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
            <MapPin className="h-3.5 w-3.5" aria-hidden />
            Território
          </p>
          <p className="font-medium text-gray-700 dark:text-gray-300">{territorio}</p>
          {(perfil?.areas ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {perfil!.areas.map((a) => (
                <span
                  key={a}
                  className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                >
                  {a}
                </span>
              ))}
            </div>
          )}
          <Link
            href="/onboarding"
            className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-brand-700 transition-colors hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300"
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden />
            Ajustar perfil
          </Link>
        </div>

        <nav className="flex flex-col gap-0.5 text-sm">
          {NAV.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`group relative flex items-center gap-2.5 rounded-lg px-3 py-2 font-medium transition-all duration-150 ${
                  active
                    ? "bg-brand-50 text-brand-800 dark:bg-brand-900/30 dark:text-brand-300"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
                }`}
              >
                {active && (
                  <span
                    className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand-600 animate-scale-in"
                    aria-hidden
                  />
                )}
                <Icon
                  className={`h-4.5 w-4.5 shrink-0 transition-transform duration-150 group-hover:scale-110 ${
                    active ? "text-brand-600 dark:text-brand-400" : "text-gray-400"
                  }`}
                  aria-hidden
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={sair}
          className="mt-auto inline-flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-gray-500 transition-colors hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/40 dark:hover:text-red-400"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Sair
        </button>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col gap-6">{children}</main>
    </div>
  );
}
