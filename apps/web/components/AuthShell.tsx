import Link from "next/link";
import type { ReactNode } from "react";

/** Logotipo textual da marca (ponto amarelo + nome). */
export function BrandMark({ size = "base" }: { size?: "base" | "lg" }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-semibold tracking-tight ${
        size === "lg" ? "text-xl" : "text-base"
      }`}
    >
      <span className="brand-dot" aria-hidden />
      Hub Capture
    </span>
  );
}

/**
 * Painel visual "spatial" da coluna direita do auth: composição em vidro
 * sobre preto com glow amarelo — sem asset externo (funciona offline).
 */
function SpatialPanel() {
  return (
    <div className="relative hidden overflow-hidden rounded-4xl bg-black lg:block">
      {/* Glows ambientes */}
      <div
        aria-hidden
        className="absolute -top-32 right-[-20%] h-[34rem] w-[34rem] rounded-full bg-brand/25 blur-[120px]"
      />
      <div
        aria-hidden
        className="absolute bottom-[-25%] left-[-15%] h-[30rem] w-[30rem] rounded-full bg-brand/15 blur-[110px]"
      />
      <div
        aria-hidden
        className="absolute left-1/3 top-1/2 h-40 w-40 rounded-full bg-brand/30 blur-[80px]"
      />

      {/* Anéis concêntricos sutis */}
      <svg
        aria-hidden
        className="absolute inset-0 h-full w-full opacity-25"
        viewBox="0 0 600 800"
        fill="none"
        preserveAspectRatio="xMidYMid slice"
      >
        <circle cx="300" cy="400" r="180" stroke="#ffd60a" strokeOpacity="0.25" />
        <circle cx="300" cy="400" r="260" stroke="#ffd60a" strokeOpacity="0.15" />
        <circle cx="300" cy="400" r="340" stroke="#ffd60a" strokeOpacity="0.08" />
      </svg>

      {/* Cartões de vidro flutuantes (produto em miniatura) */}
      <div className="absolute inset-0 flex flex-col justify-between p-10">
        <div className="float-slow ml-auto w-64 rounded-2xl border border-white/15 bg-white/10 p-4 shadow-2xl backdrop-blur-xl">
          <p className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            Recursos recebidos
          </p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-white">
            R$ 4,2 mi
          </p>
          <p className="mt-1 text-xs text-brand">FPM + Emendas · últimos 30 dias</p>
        </div>

        <div className="float-slower w-60 rounded-2xl border border-white/15 bg-white/10 p-4 shadow-2xl backdrop-blur-xl">
          <p className="text-[11px] font-medium uppercase tracking-wider text-white/50">
            Captação
          </p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-white">
            12 propostas
          </p>
          <p className="mt-1 text-xs text-white/60">
            3 com prazo esta semana
            <span className="ml-2 inline-block rounded-full bg-brand px-2 py-0.5 text-[10px] font-semibold text-brand-fg">
              alerta
            </span>
          </p>
        </div>

        <div>
          <p className="max-w-xs text-2xl font-semibold leading-snug tracking-tight text-white">
            O ciclo completo do recurso público,
            <span className="text-brand"> num só painel.</span>
          </p>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-white/55">
            Captação, recebimentos, conformidade e obras do seu território —
            curados por IA, com alertas no WhatsApp.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Shell das telas de autenticação: duas colunas — formulário à esquerda,
 * painel visual spatial à direita (oculto no mobile).
 */
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
    <main className="grid min-h-screen grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-2">
      <div className="flex flex-col justify-between py-4 sm:px-6">
        <Link href="/" className="self-start">
          <BrandMark />
        </Link>

        <div className="mx-auto w-full max-w-sm py-10">
          <h1 className="text-display text-3xl">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-ink-2">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 text-sm text-ink-2">{footer}</div>}
        </div>

        <p className="text-xs text-ink-3">
          © {new Date().getFullYear()} Hub Capture
        </p>
      </div>

      <SpatialPanel />
    </main>
  );
}
