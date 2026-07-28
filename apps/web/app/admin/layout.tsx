"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
import { api, getToken } from "@/lib/api/client";

/**
 * Shell do painel de administração (superuser). Um único lugar para gerir a
 * plataforma: providers/credenciais, usuários, convites e planos. O guard
 * consulta /users/me — quem não é admin volta para o painel comum (a API já
 * nega de qualquer forma; aqui é só UX).
 */

const NAV = [
  { href: "/admin/usuarios", label: "Usuários" },
  { href: "/admin/convites", label: "Convites" },
  { href: "/admin/planos", label: "Planos" },
  { href: "/admin/config", label: "Providers & Config" },
  { href: "/admin/fontes", label: "Fontes (diagnóstico)" },
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
        router.replace("/painel");
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

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <BrandMark />
          <p className="label-mono mt-1.5">Administração</p>
        </div>
        <Link
          href="/painel"
          className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
        >
          ← Meu painel
        </Link>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-hairline pb-3">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
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

      <div className="flex flex-1 flex-col gap-6">{children}</div>
    </div>
  );
}
