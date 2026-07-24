import Link from "next/link";
import type { ReactNode } from "react";

/** Marca: dot lime 6px + nome em peso único. */
export function BrandMark({ size = "base" }: { size?: "base" | "lg" }) {
  return (
    <span
      className={`inline-flex items-center gap-2 tracking-tight ${
        size === "lg" ? "text-xl" : "text-base"
      }`}
    >
      <span className="brand-dot" aria-hidden />
      Hub Capture
    </span>
  );
}

/**
 * Painel lateral do auth: banda escura flat em Abyssal Ink — sem gradiente,
 * sem blur, sem sombra. Hierarquia por tamanho/tracking, hairlines de 1px
 * e o acento lime racionado a dots e à seta de 40px.
 */
function LabPanel() {
  return (
    <div className="relative hidden flex-col justify-between overflow-hidden rounded-[20px] bg-abyss p-10 lg:flex">
      {/* contador de seção — a voz de sumário da página */}
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center rounded-full border border-graphite px-3 py-1 font-mono text-[13px] tracking-[-0.02em] text-graphite">
          01 / 04
        </span>
        <span className="font-mono text-[13px] tracking-[-0.02em] text-graphite">
          CICLO DO RECURSO PÚBLICO
        </span>
      </div>

      {/* headline arquitetural — peso 400, tracking negativo, ponto final */}
      <div className="py-16">
        <p className="max-w-md text-[42px] leading-[1.1] tracking-[-0.02em] text-paper">
          Captar, receber, executar, prestar contas.
        </p>
        <p className="mt-8 max-w-sm text-[18px] leading-[1.3] tracking-[-0.001em] text-lichen/70">
          O território inteiro num só painel — curado por IA, com alertas no
          WhatsApp.
        </p>
      </div>

      {/* bancada: linhas de instrumentação com dot lime + mono */}
      <div className="flex flex-col">
        {[
          ["CAPTAÇÃO", "12 propostas · 3 com prazo esta semana"],
          ["RECURSOS RECEBIDOS", "R$ 4,2 mi · FPM + emendas, 30 dias"],
          ["CONFORMIDADE", "CAUC 18/21 comprovados"],
          ["OBRAS", "7 em execução · 2 paralisadas"],
        ].map(([tag, meta]) => (
          <div
            key={tag}
            className="flex items-center justify-between border-t border-graphite py-3.5"
          >
            <span className="inline-flex items-center gap-2 font-mono text-[13px] tracking-[-0.02em] text-lichen">
              <span className="brand-dot" aria-hidden />
              {tag}
            </span>
            <span className="font-mono text-[13px] tracking-[-0.02em] text-graphite">
              {meta}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between border-t border-graphite pt-5">
          <span className="font-mono text-[13px] tracking-[-0.02em] text-graphite">
            HUBCAPTURE — PAINEL DO TERRITÓRIO
          </span>
          {/* seta 40×40: o único preenchimento lime do sistema */}
          <span
            aria-hidden
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-lime text-abyss"
          >
            →
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Shell das telas de autenticação: duas colunas — formulário à esquerda,
 * banda de laboratório à direita (oculta no mobile).
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
          <h1 className="text-[36px] leading-[1.15] tracking-[-0.02em]">{title}</h1>
          {subtitle && (
            <p className="mt-3 text-sm leading-relaxed text-ink-2">{subtitle}</p>
          )}
          <div className="mt-10">{children}</div>
          {footer && <div className="mt-10 text-sm text-ink-2">{footer}</div>}
        </div>

        <p className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
          © {new Date().getFullYear()} Hub Capture
        </p>
      </div>

      <LabPanel />
    </main>
  );
}
