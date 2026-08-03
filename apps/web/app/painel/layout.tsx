"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cx } from "@/components/ui";
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
  { href: "/painel/curadoria", label: "Favoritos e pastas" },
  { href: "/painel/alertas", label: "Alertas", badge: "alertas" as const },
  { href: "/painel/chat", label: "Copiloto" },
  { href: "/painel/conta", label: "Minha conta" },
];

const PAPEL_LABEL: Record<string, string> = {
  parlamentar: "Parlamentar",
  executivo: "Executivo",
  equipe: "Equipe",
};

export default function PainelLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [naoLidos, setNaoLidos] = useState(0);
  const [menuAberto, setMenuAberto] = useState(false);

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

  const carregarAlertas = useCallback(async () => {
    const { data } = await api.GET("/api/v1/alertas", {
      params: { query: { nao_lidos: true } },
    });
    if (Array.isArray(data)) setNaoLidos(data.length);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    void carregarAlertas();
  }, [carregarAlertas, pathname]);

  // O drawer não pode sobreviver à navegação nem ao Esc.
  useEffect(() => setMenuAberto(false), [pathname]);
  useEffect(() => {
    if (!menuAberto) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuAberto(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuAberto]);

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

  const nav = (
    <nav className="flex flex-col gap-0.5 text-sm">
      {NAV.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "flex items-center justify-between gap-2 rounded-md px-3 py-2 transition",
              active
                ? "bg-brand font-medium text-brand-fg"
                : "text-ink-2 hover:bg-surface hover:text-ink",
            )}
          >
            {item.label}
            {item.badge === "alertas" && naoLidos > 0 && (
              <span
                className={cx(
                  "num rounded-full px-1.5 text-xs font-semibold",
                  active ? "bg-white/25 text-brand-fg" : "bg-danger text-white",
                )}
              >
                {naoLidos}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );

  const territorioBox = (
    <div className="rounded-lg border border-line bg-surface p-3 text-sm">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
        Território
      </p>
      <p className="text-ink-2">{territorio}</p>
      {(perfil?.areas ?? []).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {perfil!.areas.map((a) => (
            <span
              key={a}
              className="rounded-full bg-surface-2 px-2 py-0.5 text-xs capitalize text-ink-2"
            >
              {a}
            </span>
          ))}
        </div>
      )}
      <Link
        href="/onboarding"
        className="mt-2 inline-block text-xs text-brand underline underline-offset-2"
      >
        Ajustar perfil
      </Link>
    </div>
  );

  return (
    <div className="min-h-screen bg-bg">
      {/* Topbar — abaixo de md ela é a navegação; a sidebar não empilha mais
          acima do conteúdo, que consumia a primeira dobra inteira no celular. */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-bg/95 px-4 py-3 backdrop-blur md:hidden">
        <button
          type="button"
          onClick={() => setMenuAberto((v) => !v)}
          aria-expanded={menuAberto}
          aria-controls="menu-painel"
          className="flex size-9 items-center justify-center rounded-md border border-line text-ink"
        >
          <span className="sr-only">{menuAberto ? "Fechar menu" : "Abrir menu"}</span>
          <span aria-hidden className="text-lg leading-none">
            {menuAberto ? "✕" : "☰"}
          </span>
        </button>
        <Link href="/painel" className="font-bold text-ink">
          Hub Capture
        </Link>
        {naoLidos > 0 && (
          <Link
            href="/painel/alertas"
            className="num ml-auto rounded-full bg-danger px-2 py-0.5 text-xs font-semibold text-white"
          >
            {naoLidos} {naoLidos === 1 ? "alerta" : "alertas"}
          </Link>
        )}
      </header>

      {menuAberto && (
        <div
          id="menu-painel"
          className="border-b border-line bg-bg px-4 py-4 md:hidden"
        >
          <div className="flex flex-col gap-4">
            {territorioBox}
            {nav}
            <div className="flex items-center justify-between">
              <ThemeToggle />
              <button onClick={sair} className="text-xs text-muted underline">
                Sair
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 md:flex-row md:gap-8">
        <aside className="hidden shrink-0 flex-col gap-6 md:flex md:w-60">
          <div>
            <Link href="/painel" className="text-lg font-bold text-ink">
              Hub Capture
            </Link>
            <p className="mt-0.5 text-[11px] uppercase tracking-wider text-muted">
              {perfil?.papel ? (PAPEL_LABEL[perfil.papel] ?? perfil.papel) : "Meu perfil"}
            </p>
          </div>

          {territorioBox}
          {nav}

          <div className="mt-auto flex flex-col items-start gap-3 pt-4">
            <ThemeToggle />
            <button onClick={sair} className="text-xs text-muted underline">
              Sair
            </button>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col gap-5">{children}</main>
      </div>
    </div>
  );
}
