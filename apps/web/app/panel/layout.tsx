"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
import DynamicIsland from "@/components/DynamicIsland";
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
  { href: "/panel", label: "Meu painel", exact: true },
  { href: "/panel/funding", label: "Captação", modulo: "captacao" },
  { href: "/panel/my-proposals", label: "Minhas Propostas", modulo: "captacao" },
  { href: "/panel/transfers", label: "Recursos recebidos", modulo: "recebidos" },
  {
    href: "/panel/compliance",
    label: "Conformidade fiscal",
    modulo: "conformidade",
  },
  { href: "/panel/works", label: "Obras", modulo: "obras" },
  { href: "/panel/alerts", label: "Alertas" },
  { href: "/panel/copilot", label: "Copiloto", modulo: "copiloto" },
  { href: "/panel/account", label: "Minha conta" },
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
  const [admin, setAdmin] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const [{ data }, me] = await Promise.all([
        api.GET("/api/v1/profile"),
        api.GET("/api/v1/users/me"),
      ]);
      if (data) setPerfil(data as Perfil);
      setAdmin(Boolean((me.data as { is_superuser?: boolean } | undefined)?.is_superuser));
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
          <Link href="/panel">
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
                className={`nav-item ${active ? "nav-item-active" : ""}`}
              >
                {item.label}
              </Link>
            );
          })}
          {admin && (
            <Link href="/admin/users" className="nav-item">
              Administração
            </Link>
          )}
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

      {/* Copiloto em Dynamic Island — persiste em TODAS as telas do painel,
          só depois do onboarding (precisa de território p/ ter o que consultar). */}
      {municipios.length > 0 && <DynamicIsland />}
    </div>
  );
}
