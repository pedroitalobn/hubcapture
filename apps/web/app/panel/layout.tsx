"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DynamicIsland from "@/components/DynamicIsland";
import { TerritorioFiltro } from "@/components/TerritorioFiltro";
import { ThemeToggle } from "@/components/ThemeToggle";
import { IconeNav, type NomeIcone } from "@/components/icons";
import { api, clearTokens, getToken } from "@/lib/api/client";
import { HelpProvider } from "@/lib/help";
import { TerritorioProvider, useTerritorio } from "@/lib/territorio";
import { OrigemProvider } from "@/lib/origem";
import {
  OrigemRecursoFiltro,
  OrigemRecursoTitulo,
} from "@/components/OrigemRecursoFiltro";

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
// Itens com `modulo` só aparecem se o módulo estiver ativo (painel admin).
const NAV: {
  href: string;
  label: string;
  icone: NomeIcone;
  exact?: boolean;
  modulo?: string;
}[] = [
  { href: "/panel", label: "Meu painel", icone: "painel", exact: true },
  {
    href: "/panel/funding",
    label: "Propostas",
    icone: "propostas",
    modulo: "captacao",
  },
  // Minhas Propostas é ACOMPANHAMENTO (favoritas do cache) — panel-core, não
  // exploração: fica no menu mesmo com o módulo captação desligado (§40).
  { href: "/panel/my-proposals", label: "Minhas Propostas", icone: "favoritas" },
  {
    href: "/panel/opportunities",
    label: "Oportunidades",
    icone: "oportunidades",
    modulo: "oportunidades",
  },
  {
    href: "/panel/regularity",
    label: "Regularidade",
    icone: "regularidade",
    modulo: "regularidade",
  },
  {
    href: "/panel/transfers",
    label: "Recursos recebidos",
    icone: "recebidos",
    modulo: "recebidos",
  },
  {
    href: "/panel/compliance",
    label: "Conformidade fiscal",
    icone: "conformidade",
    modulo: "conformidade",
  },
  { href: "/panel/works", label: "Obras", icone: "obras", modulo: "obras" },
  {
    href: "/panel/alerts",
    label: "Alertas",
    icone: "alertas",
    modulo: "alertas",
  },
  {
    href: "/panel/contacts",
    label: "Agenda de contatos",
    icone: "contatos",
    modulo: "contatos",
  },
  {
    href: "/panel/copilot",
    label: "Copiloto",
    icone: "copiloto",
    modulo: "copiloto",
  },
  {
    href: "/panel/advisory",
    label: "Assessoria",
    icone: "assessoria",
    modulo: "assessoria",
  },
  { href: "/panel/class", label: "Class", icone: "class", modulo: "ajuda" },
  { href: "/panel/account", label: "Minha conta", icone: "conta" },
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
      <OrigemProvider>
      {/* O mapa de hints (ⓘ) é estado de todo o painel, como o território:
          carrega uma vez e os <Hint/> das telas consultam localmente. */}
      <HelpProvider>
        <PainelShell>{children}</PainelShell>
      </HelpProvider>
      </OrigemProvider>
    </TerritorioProvider>
  );
}

function PainelShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { perfil, municipios, selecionados } = useTerritorio();
  const [admin, setAdmin] = useState(false);
  // Sidebar vira gaveta abaixo de 1024px (guia §7); fecha a cada navegação.
  const [gaveta, setGaveta] = useState(false);

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

  useEffect(() => {
    setGaveta(false);
  }, [pathname]);

  function sair() {
    clearTokens();
    router.replace("/login");
  }

  const itens = NAV.filter(
    (item) => !item.modulo || (perfil?.modulos ?? []).includes(item.modulo),
  );
  const atual = itens.find((item) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href),
  );

  return (
    <div className={`app-shell ${gaveta ? "drawer-open" : ""}`}>
      {/* Véu da gaveta no mobile — clicar fora fecha o menu */}
      {gaveta && (
        <button
          type="button"
          aria-label="Fechar menu"
          onClick={() => setGaveta(false)}
          className="fixed inset-0 z-50 bg-brand-dark/50 lg:hidden"
        />
      )}

      <aside className="sidebar">
        <Link href="/panel" className="sidebar-brand px-2 py-1">
          <span className="brand-dot" aria-hidden />
          Hub Capture
        </Link>

        {/* Território do perfil — a chave de tudo é o município, não a fonte.
            O filtro escolhe QUAIS dos municípios do onboarding entram no
            painel agora; o recorte vale para todas as lentes do menu. */}
        <div className="sidebar-box text-sm">
          <p className="label-mono mb-1.5">
            Território
            {selecionados.length > 0 && municipios.length > 1 && (
              <span className="ml-1.5 normal-case">(filtrado)</span>
            )}
          </p>
          <TerritorioFiltro />
          {/* Origem do recurso — de QUAL fonte veio o registro (TransfereGov,
              FNS…). Multi-select: o recorte soma origens; vazio = todas. */}
          <OrigemRecursoTitulo />
          <OrigemRecursoFiltro />
          {(perfil?.areas ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {perfil!.areas.map((a) => (
                <span
                  key={a}
                  className="inline-flex items-center gap-1.5 rounded border border-hairline px-2 py-0.5 text-[11px]"
                >
                  <span className="brand-dot" aria-hidden />
                  {a}
                </span>
              ))}
            </div>
          )}
          {/* Conta demo: o território é semeado pela plataforma e o backend
              bloqueia o onboarding — sem o link, sem beco sem saída. */}
          {!perfil?.demo && (
            <Link href="/onboarding" className="link-soft mt-3 inline-block text-[12px]">
              Ajustar perfil →
            </Link>
          )}
        </div>

        <nav className="flex flex-col gap-0.5">
          <p className="label-mono px-3 pb-1 pt-2">Visão geral</p>
          {itens.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${active ? "nav-item-active" : ""}`}
              >
                <IconeNav nome={item.icone} />
                {item.label}
              </Link>
            );
          })}
          {admin && (
            <Link href="/admin/users" className="nav-item">
              <IconeNav nome="admin" />
              Administração
            </Link>
          )}
        </nav>

        <div className="mt-auto flex flex-col items-start gap-3 border-t border-hairline pt-4">
          {/* Tema claro/escuro — a escolha persiste em `hub_tema` e vale
              para o app inteiro (boot script no layout raiz). */}
          <ThemeToggle />
          <button onClick={sair} className="link-soft self-start text-[12px]">
            Sair da conta
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <button
            type="button"
            onClick={() => setGaveta((v) => !v)}
            aria-label="Abrir menu"
            className="icon-btn lg:hidden"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
          {/* Trilha: território → tela. É o que diz ONDE o gestor está — a
              marca já ficou na sidebar, não precisa se repetir aqui. */}
          <nav className="flex min-w-0 items-center gap-2 text-[13px] text-ink-3">
            <span className="truncate">
              {municipios.length > 0
                ? municipios
                    .filter((m) => selecionados.length === 0 || selecionados.includes(m.ibge))
                    .slice(0, 2)
                    .map((m) => `${m.nome ?? m.ibge}${m.uf ? `/${m.uf}` : ""}`)
                    .join(" · ") || "Meu território"
                : "Meu território"}
            </span>
            <span aria-hidden className="h-1 w-1 shrink-0 rounded-full bg-ink-3" />
            <b className="truncate font-semibold text-ink">
              {atual?.label ?? "Meu painel"}
            </b>
          </nav>
          <span className="ml-auto text-[13px] text-ink-3">
            {perfil?.papel ? PAPEL_LABEL[perfil.papel] ?? perfil.papel : ""}
          </span>
        </header>

        <main className="mx-auto flex w-full min-w-0 max-w-[1600px] flex-1 flex-col px-4 py-5 sm:px-6 lg:px-8">
          {/* Faixa do sandbox: dados são REAIS (cache de captação); o que é
              simulado são as ações de conta — o backend bloqueia o destrutivo. */}
          {perfil?.demo && (
            <div className="card mb-4 flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm text-ink-2">
              <span>
                <strong className="text-ink">Ambiente de demonstração</strong> —
                dados reais de captação; alterações de conta ficam desativadas.
              </span>
              <Link href="/signup" className="link-soft text-[12px]">
                Criar minha conta →
              </Link>
            </div>
          )}
          {/* `key={pathname}` remonta o wrapper a cada navegação, então a
              animação de entrada REEXECUTA — sem isso o layout persiste no App
              Router e a transição só aconteceria no primeiro carregamento. */}
          <div
            key={pathname}
            className="anim-page stagger flex min-w-0 flex-1 flex-col gap-6"
          >
            {children}
          </div>
        </main>
      </div>

      {/* Copiloto em Dynamic Island — persiste em TODAS as telas do painel,
          só depois do onboarding e só quando o módulo está no plano (§39). */}
      {municipios.length > 0 &&
        (perfil?.modulos ?? []).includes("copiloto") && <DynamicIsland />}
    </div>
  );
}
