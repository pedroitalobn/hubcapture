"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
import DynamicIsland from "@/components/DynamicIsland";
import { TerritorioFiltro } from "@/components/TerritorioFiltro";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api, clearTokens, getToken } from "@/lib/api/client";
import { HelpProvider } from "@/lib/help";
import { TerritorioProvider, useTerritorio } from "@/lib/territorio";

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
  { href: "/panel/alerts", label: "Alertas", modulo: "alertas" },
  { href: "/panel/contacts", label: "Agenda de contatos", modulo: "contatos" },
  { href: "/panel/copilot", label: "Copiloto", modulo: "copiloto" },
  { href: "/panel/advisory", label: "Assessoria", modulo: "assessoria" },
  { href: "/panel/class", label: "Class", modulo: "ajuda" },
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
  // O território (municípios do perfil + recorte ativo) é estado de TODO o
  // painel: o provider carrega o perfil uma vez e as telas leem daqui.
  return (
    <TerritorioProvider>
      {/* O mapa de hints (ⓘ) é estado de todo o painel, como o território:
          carrega uma vez e os <Hint/> das telas consultam localmente. */}
      <HelpProvider>
        <PainelShell>{children}</PainelShell>
      </HelpProvider>
    </TerritorioProvider>
  );
}

function PainelShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { perfil, municipios, selecionados } = useTerritorio();
  const [admin, setAdmin] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const me = await api.GET("/api/v1/users/me");
      setAdmin(Boolean((me.data as { is_superuser?: boolean } | undefined)?.is_superuser));
    })();
  }, [router]);

  function sair() {
    clearTokens();
    router.replace("/login");
  }

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

        {/* Território do perfil — a chave de tudo é o município, não a fonte.
            O filtro escolhe QUAIS dos municípios do onboarding entram no
            painel agora; o recorte vale para todas as lentes do menu. */}
        <div className="border-t border-hairline pt-4 text-sm">
          <p className="label-mono mb-1.5">
            Território
            {selecionados.length > 0 && municipios.length > 1 && (
              <span className="ml-1.5 normal-case text-ink-2">(filtrado)</span>
            )}
          </p>
          <TerritorioFiltro />
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

        <div className="mt-auto flex flex-col items-start gap-3">
          {/* Tema claro/escuro — a escolha persiste em `hub_tema` e vale
              para o app inteiro (boot script no layout raiz). */}
          <ThemeToggle />
          <button
            onClick={sair}
            className="self-start font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 transition-colors hover:text-ink"
          >
            Sair da conta
          </button>
        </div>
      </aside>

      <main className="mx-auto flex w-full min-w-0 max-w-[1600px] flex-1 flex-col py-2">
        {/* `key={pathname}` remonta o wrapper a cada navegação, então a
            animação de entrada REEXECUTA — sem isso o layout persiste no App
            Router e a transição só aconteceria no primeiro carregamento.
            Uma linha aqui cobre todas as telas do painel. */}
        <div
          key={pathname}
          className="anim-page flex min-w-0 flex-1 flex-col gap-6"
        >
          {children}
        </div>
      </main>

      {/* Copiloto em Dynamic Island — persiste em TODAS as telas do painel,
          só depois do onboarding (precisa de território p/ ter o que consultar)
          e só quando o módulo copiloto está no plano do usuário (§39). */}
      {municipios.length > 0 &&
        (perfil?.modulos ?? []).includes("copiloto") && <DynamicIsland />}
    </div>
  );
}
