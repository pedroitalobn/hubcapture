"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconeNav, type NomeIcone } from "@/components/icons";
import { api, getToken } from "@/lib/api/client";

/**
 * Shell do painel de administração (superuser). Um único lugar para gerir a
 * plataforma: providers/credenciais, usuários, convites e planos. O guard
 * consulta /users/me — quem não é admin volta para o painel comum (a API já
 * nega de qualquer forma; aqui é só UX).
 */

/* Menu em GRUPOS: onze abas numa linha só de pílulas não diziam o que era
   plataforma, o que era conteúdo e o que era diagnóstico — e no notebook a
   linha quebrava em duas. Agora é a mesma sidebar escura do painel (guia §7),
   com as seções nomeadas. */
const NAV: { titulo: string; itens: { href: string; label: string; icone: NomeIcone }[] }[] = [
  {
    titulo: "Pessoas",
    itens: [
      { href: "/admin/users", label: "Usuários", icone: "conta" },
      { href: "/admin/invites", label: "Convites", icone: "contatos" },
      { href: "/admin/plans", label: "Planos", icone: "favoritas" },
    ],
  },
  {
    titulo: "Plataforma",
    itens: [
      { href: "/admin/config", label: "Providers & Config", icone: "admin" },
      { href: "/admin/modules", label: "Módulos", icone: "painel" },
    ],
  },
  {
    titulo: "Dados",
    itens: [
      { href: "/admin/sources", label: "Fontes (diagnóstico)", icone: "recebidos" },
      { href: "/admin/siconv", label: "Pacote SIconv", icone: "propostas" },
    ],
  },
  {
    titulo: "Conteúdo",
    itens: [
      { href: "/admin/class", label: "Class", icone: "class" },
      { href: "/admin/advisory", label: "Assessoria", icone: "assessoria" },
      { href: "/admin/directory", label: "Diretório institucional", icone: "contatos" },
      { href: "/admin/requests", label: "Demandas", icone: "alertas" },
    ],
  },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const { data, error } = await api.GET("/api/v1/users/me");
      const me = data as { is_superuser?: boolean } | undefined;
      if (error || !me?.is_superuser) {
        router.replace("/panel");
        return;
      }
      setPronto(true);
    })();
  }, [router]);

  if (!pronto) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-ink-3">
        Verificando permissões…
      </main>
    );
  }

  const atual = NAV.flatMap((g) => g.itens).find((item) =>
    pathname.startsWith(item.href),
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/panel" className="sidebar-brand px-2 py-1">
          <span className="brand-dot" aria-hidden />
          Hub Capture
        </Link>
        <p className="label-mono px-2 -mt-2">Administração</p>

        <nav className="flex flex-col gap-0.5">
          {NAV.map((grupo) => (
            <div key={grupo.titulo} className="flex flex-col gap-0.5">
              <p className="label-mono px-3 pb-1 pt-3">{grupo.titulo}</p>
              {grupo.itens.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-item ${pathname.startsWith(item.href) ? "nav-item-active" : ""}`}
                >
                  <IconeNav nome={item.icone} />
                  {item.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>

        {/* O retorno ao painel fecha a coluna: é a saída da administração. */}
        <div className="mt-auto border-t border-hairline pt-4">
          <Link href="/panel" className="nav-item">
            <IconeNav nome="painel" />
            Voltar ao Meu painel
          </Link>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <nav className="flex min-w-0 items-center gap-2 text-[13px] text-ink-3">
            <span>Administração</span>
            <span aria-hidden className="h-1 w-1 shrink-0 rounded-full bg-ink-3" />
            <b className="truncate font-semibold text-ink">
              {atual?.label ?? "Plataforma"}
            </b>
          </nav>
        </header>

        <main className="mx-auto flex w-full min-w-0 max-w-[1400px] flex-1 flex-col px-4 py-5 sm:px-6 lg:px-8">
          {/* mesma mecânica do painel: chave por rota reexecuta a entrada */}
          <div key={pathname} className="anim-page stagger flex flex-1 flex-col gap-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
