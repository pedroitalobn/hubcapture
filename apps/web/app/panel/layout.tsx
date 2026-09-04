"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import DynamicIsland from "@/components/DynamicIsland";
import { FiltrosPainel, filtrosDaRota } from "@/components/FiltrosPainel";
import { MenuConta } from "@/components/MenuConta";
import { IconeNav, type NomeIcone } from "@/components/icons";
import { api, clearTokens, getToken } from "@/lib/api/client";
import { HelpProvider } from "@/lib/help";
import {
  rotuloMunicipio,
  TerritorioProvider,
  useTerritorio,
} from "@/lib/territorio";
import { OrigemProvider } from "@/lib/origem";
import { AnoProvider } from "@/lib/ano";

// A navegação NÃO é por fonte de dados — é o ciclo do recurso público, sempre
// recortado pelo território do usuário (via RLS). Cada item é uma LENTE sobre
// o(s) município(s) do perfil, não uma aba de plataforma de governo.
// Itens com `modulo` só aparecem se o módulo estiver ativo (painel admin).
//
// As lentes agora vêm AGRUPADAS por etapa do ciclo: quatorze linhas de texto
// do mesmo peso não se leem, e o gestor voltava ao item pela posição na lista
// em vez de pelo nome. Grupo sem nenhum item visível (todos os módulos
// desligados) não desenha o rótulo — cabeçalho sozinho é ruído.
interface ItemNav {
  href: string;
  label: string;
  icone: NomeIcone;
  exact?: boolean;
  modulo?: string;
  /** Item que carrega contagem de pendência (alertas não lidos). */
  badge?: "alertas";
}

const NAV: { titulo?: string; itens: ItemNav[] }[] = [
  {
    itens: [{ href: "/panel", label: "Meu painel", icone: "painel", exact: true }],
  },
  {
    titulo: "Captação",
    itens: [
      {
        href: "/panel/funding",
        label: "Propostas",
        icone: "propostas",
        modulo: "captacao",
      },
      // Minhas Propostas é ACOMPANHAMENTO (favoritas do cache) — panel-core,
      // não exploração: fica no menu mesmo com o módulo captação desligado.
      {
        href: "/panel/my-proposals",
        label: "Minhas Propostas",
        icone: "favoritas",
      },
      {
        href: "/panel/opportunities",
        label: "Oportunidades",
        icone: "oportunidades",
        modulo: "oportunidades",
      },
    ],
  },
  {
    titulo: "O município",
    itens: [
      {
        href: "/panel/transfers",
        label: "Recursos recebidos",
        icone: "recebidos",
        modulo: "recebidos",
      },
      { href: "/panel/works", label: "Obras", icone: "obras", modulo: "obras" },
      {
        href: "/panel/regularity",
        label: "Regularidade",
        icone: "regularidade",
        modulo: "regularidade",
      },
      {
        href: "/panel/compliance",
        label: "Conformidade fiscal",
        icone: "conformidade",
        modulo: "conformidade",
      },
    ],
  },
  {
    titulo: "Acompanhamento",
    itens: [
      {
        href: "/panel/alerts",
        label: "Alertas",
        icone: "alertas",
        modulo: "alertas",
        badge: "alertas",
      },
      {
        href: "/panel/contacts",
        label: "Agenda de contatos",
        icone: "contatos",
        modulo: "contatos",
      },
    ],
  },
  {
    titulo: "Apoio",
    itens: [
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
    ],
  },
];

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
        {/* A ano é o 3º recorte global da barra (§60) — a tela publica as
            opções que vieram do feed, o provider guarda a escolha. */}
        <AnoProvider>
          {/* O mapa de hints (ⓘ) é estado de todo o painel, como o território:
              carrega uma vez e os <Hint/> das telas consultam localmente. */}
          <HelpProvider>
            <PainelShell>{children}</PainelShell>
          </HelpProvider>
        </AnoProvider>
      </OrigemProvider>
    </TerritorioProvider>
  );
}

function PainelShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { perfil, municipios, ativos: municipiosAtivos } = useTerritorio();
  const [admin, setAdmin] = useState(false);
  const [naoLidos, setNaoLidos] = useState(0);
  // Sidebar vira gaveta abaixo de 1024px; fecha a cada navegação.
  const [gaveta, setGaveta] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const me = await api.GET("/api/v1/users/me");
      setAdmin(
        Boolean((me.data as { is_superuser?: boolean } | undefined)?.is_superuser),
      );
    })();
  }, [router]);

  // Contagem de alertas não lidos no próprio menu: a pendência precisa
  // aparecer ONDE se navega, não só depois de abrir a central. Recarrega a
  // cada navegação (marcar como lido em /panel/alerts atualiza o número ao
  // sair da tela) e degrada em silêncio — badge não é motivo de erro na tela.
  const contarAlertas = useCallback(async () => {
    const { data } = await api.GET("/api/v1/alerts", {
      params: { query: { nao_lidos: true, limite: 50 } } as never,
    });
    setNaoLidos(Array.isArray(data) ? data.length : 0);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    if (!(perfil?.modulos ?? []).includes("alertas")) return;
    void contarAlertas();
  }, [contarAlertas, perfil, pathname]);

  useEffect(() => {
    setGaveta(false);
  }, [pathname]);

  const sair = useCallback(() => {
    clearTokens();
    router.replace("/login");
  }, [router]);

  const ativos = (perfil?.modulos ?? []) as string[];
  // O território só entra na trilha quando NÃO há seletor de município na
  // tela (um município só, ou rota sem recorte): senão o mesmo dado
  // apareceria em dois lugares, e o do cabeçalho não seria clicável.
  const territorioNaTrilha =
    !filtrosDaRota(pathname).municipio || municipios.length < 2;
  const rotuloTerritorio = municipiosAtivos
    .slice(0, 2)
    .map(rotuloMunicipio)
    .join(" · ");
  const grupos = NAV.map((g) => ({
    ...g,
    itens: g.itens.filter((i) => !i.modulo || ativos.includes(i.modulo)),
  })).filter((g) => g.itens.length > 0);
  const atual = grupos
    .flatMap((g) => g.itens)
    .find((item) =>
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

        <nav className="flex flex-col gap-0.5" aria-label="Seções do painel">
          {grupos.map((grupo, i) => (
            <div key={grupo.titulo ?? `g${i}`} className="flex flex-col gap-0.5">
              {grupo.titulo && (
                <p className="label-mono px-3 pb-1 pt-3">{grupo.titulo}</p>
              )}
              {grupo.itens.map((item) => {
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
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.badge === "alertas" && naoLidos > 0 && (
                      <span
                        className="nav-badge"
                        title={`${naoLidos} ${naoLidos === 1 ? "alerta não lido" : "alertas não lidos"}`}
                      >
                        {naoLidos > 99 ? "99+" : naoLidos}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="mt-auto border-t border-hairline pt-3">
          <MenuConta
            nome={perfil?.nome}
            papel={perfil?.papel}
            municipios={municipios.length}
            admin={admin}
            demo={perfil?.demo}
            onSair={sair}
          />
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
          {/* Trilha: a seção em que o gestor está. O h1 da página rola para
              fora; o cabeçalho é grudado e mantém o "onde estou" na tela. */}
          <nav className="flex min-w-0 items-center gap-2 text-[13px] text-ink-3">
            <span className="hidden min-w-0 shrink truncate sm:inline">
              {territorioNaTrilha && rotuloTerritorio
                ? rotuloTerritorio
                : "Hub Capture"}
            </span>
            <span
              aria-hidden
              className="hidden h-1 w-1 shrink-0 rounded-full bg-ink-3 sm:inline-block"
            />
            <b className="truncate font-semibold text-ink">
              {atual?.label ?? "Meu painel"}
            </b>
          </nav>

          <div className="ml-auto flex items-center gap-1.5">
            {ativos.includes("alertas") && (
              <Link
                href="/panel/alerts"
                className="icon-btn relative"
                aria-label={
                  naoLidos > 0
                    ? `${naoLidos} alertas não lidos`
                    : "Central de alertas"
                }
                title="Central de alertas"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8a6 6 0 10-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9z" />
                  <path d="M10.5 21h3" />
                </svg>
                {naoLidos > 0 && (
                  <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-[var(--danger-solid)] px-1 text-[10px] font-bold leading-none text-white">
                    {naoLidos > 9 ? "9+" : naoLidos}
                  </span>
                )}
              </Link>
            )}
          </div>
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

          {/* O recorte GLOBAL (território + origem) saiu do trilho e virou a
              barra de filtros da tela — §33/§33b continuam valendo, o que
              mudou é onde o gestor mexe neles. */}
          <FiltrosPainel pathname={pathname} />

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
      {municipios.length > 0 && ativos.includes("copiloto") && <DynamicIsland />}
    </div>
  );
}
