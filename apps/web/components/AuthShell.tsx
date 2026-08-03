import Link from "next/link";
import type { ReactNode } from "react";

/** Moldura comum das telas de autenticação — mesma marca, mesmo respiro. */
export function AuthShell({
  titulo,
  descricao,
  children,
  rodape,
}: {
  titulo: string;
  descricao?: string;
  children: ReactNode;
  rodape?: ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center gap-6 px-6 py-10">
      <div className="flex flex-col gap-1">
        <Link
          href="/"
          className="text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-brand"
        >
          Hub Capture
        </Link>
        <h1 className="text-2xl font-bold tracking-tight text-ink">{titulo}</h1>
        {descricao && <p className="text-sm text-muted">{descricao}</p>}
      </div>
      {children}
      {rodape && <div className="text-sm text-muted">{rodape}</div>}
    </main>
  );
}
