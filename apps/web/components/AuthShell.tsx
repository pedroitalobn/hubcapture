import { Landmark } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

/** Casca das telas de autenticação: logo + card central com entrada animada. */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 py-10">
      <Link href="/" className="group flex flex-col items-center gap-2 animate-fade-up">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-md transition-transform duration-200 group-hover:scale-105">
          <Landmark className="h-6 w-6" aria-hidden />
        </span>
        <span className="text-sm font-semibold tracking-tight text-gray-500">
          Hub Capture
        </span>
      </Link>

      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900 [animation-delay:80ms]">
        <div className="mb-5">
          <h1 className="text-xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
        </div>
        {children}
      </div>

      {footer && (
        <div className="text-sm text-gray-500 animate-fade-up [animation-delay:160ms]">
          {footer}
        </div>
      )}
    </main>
  );
}

/** Input com ícone à esquerda, para os formulários de auth. */
export const AUTH_INPUT =
  "w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950";
