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
}

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
const NAV = [
  { href: "/painel", label: "Meu painel", exact: true, icon: IconHome },
  { href: "/painel/captacao", label: "Captação", icon: IconTarget },
  { href: "/painel/repasses", label: "Recursos recebidos", icon: IconCoins },
  { href: "/painel/conformidade", label: "Conformidade fiscal", icon: IconShield },
  { href: "/painel/obras", label: "Obras", icon: IconBuilding },
  { href: "/painel/chat", label: "Copiloto", icon: IconSpark },
  { href: "/painel/conta", label: "Minha conta", icon: IconUser },
];

const PAPEL_LABEL: Record<string, string> = {
  parlamentar: "Parlamentar",
  executivo: "Executivo",
  equipe: "Equipe",
};

function IconHome({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
    </svg>
  );
}
function IconTarget({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </svg>
  );
}
function IconCoins({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className}>
      <ellipse cx="12" cy="6.5" rx="7" ry="3.5" />
      <path d="M5 6.5V12c0 1.93 3.13 3.5 7 3.5s7-1.57 7-3.5V6.5" />
      <path d="M5 12v5.5c0 1.93 3.13 3.5 7 3.5s7-1.57 7-3.5V12" />
    </svg>
  );
}
function IconShield({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 3 4.5 6v5c0 4.7 3.2 8.4 7.5 10 4.3-1.6 7.5-5.3 7.5-10V6L12 3Z" />
      <path d="m9 11.5 2.2 2.2L15.5 9.4" />
    </svg>
  );
}
function IconBuilding({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4 21h16" />
      <path d="M6 21V5.5L14 3v18" />
      <path d="M14 8.5 18 10v11" />
      <path d="M9 8h2M9 12h2M9 16h2" />
    </svg>
  );
}
function IconSpark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}
function IconUser({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 21c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
    </svg>
  );
}

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
      <aside className="glass-panel sticky top-6 flex h-fit shrink-0 flex-col gap-6 self-start p-5 max-md:static md:w-64">
        <div>
          <Link href="/painel" className="flex items-center gap-2 text-lg font-bold">
            <span className="glow-dot text-brand" />
            <span className="text-gradient">Hub Capture</span>
          </Link>
          <p className="mt-1 text-xs uppercase tracking-widest text-gray-500">
            {perfil?.papel ? PAPEL_LABEL[perfil.papel] ?? perfil.papel : "Meu perfil"}
          </p>
        </div>

        {/* Território do perfil — a chave de tudo é o município, não a fonte. */}
        <div className="glass-card p-3 text-sm">
          <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-gray-500">
            Território
          </p>
          <p className="text-gray-300">{territorio}</p>
          {(perfil?.areas ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {perfil!.areas.map((a) => (
                <span key={a} className="chip px-2 py-0.5 text-xs">
                  {a}
                </span>
              ))}
            </div>
          )}
          <Link
            href="/onboarding"
            className="mt-2 inline-block text-xs text-brand transition hover:brightness-125"
          >
            Ajustar perfil
          </Link>
        </div>

        <nav className="flex flex-col gap-1 text-sm">
          {NAV.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`pressable group relative flex items-center gap-2.5 rounded-xl px-3 py-2 transition ${
                  active
                    ? "bg-white/10 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,.08)]"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-gradient-to-b from-indigo-400 to-sky-400 shadow-[0_0_12px_rgba(99,102,241,.9)]" />
                )}
                <Icon
                  className={`h-4.5 w-4.5 shrink-0 transition ${
                    active ? "text-brand" : "text-gray-500 group-hover:text-gray-300"
                  }`}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={sair}
          className="mt-auto text-left text-xs text-gray-500 transition hover:text-gray-300"
        >
          Sair
        </button>
      </aside>

      <main
        key={pathname}
        className="animate-fade-up flex min-w-0 flex-1 flex-col gap-6"
      >
        {children}
      </main>
    </div>
  );
}
