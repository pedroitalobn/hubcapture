import Link from "next/link";
import type { ReactNode } from "react";

/** Marca: dot lime 6px + nome em peso único. */
export function BrandMark({ size = "base" }: { size?: "base" | "lg" }) {
  return (
    <span
      className={`inline-flex items-center gap-2 tracking-tight ${
        size === "lg" ? "text-3xl font-medium" : "text-base"
      }`}
    >
      <span className="brand-dot" aria-hidden />
      Hub Capture
    </span>
  );
}

/**
 * Coluna de imagem do login: imagem gerada (topografia do território em
 * lime sobre abyssal ink) como fundo full-bleed. Se o arquivo
 * /login-hero.jpg ainda não existir, o fundo abyss segura o visual.
 */
function ImagePanel() {
  return (
    <div
      className="anim-page-delayed relative hidden overflow-hidden rounded-[20px] border border-hairline bg-abyss bg-cover bg-center lg:block"
      style={{
        // tenta o asset gerado (Magnific); sem ele, cai no SVG topográfico
        backgroundImage: "url('/login-hero.jpg'), url('/login-hero.svg')",
      }}
    >
      {/* rodapé da imagem: marca + assinatura em mono */}
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-abyss/80 to-transparent p-8">
        <span className="inline-flex items-center gap-2 font-mono text-[13px] tracking-[-0.02em] text-paper">
          <span className="brand-dot" aria-hidden />
          HUB CAPTURE
        </span>
        <span className="font-mono text-[13px] tracking-[-0.02em] text-lichen/80">
          PAINEL DO TERRITÓRIO
        </span>
      </div>
    </div>
  );
}

/**
 * Banda de bancada (telas de auth secundárias): Abyssal Ink flat com
 * contador de seção, headline arquitetural e linhas de instrumentação.
 */
function LabPanel() {
  return (
    <div className="anim-page-delayed relative hidden flex-col justify-between overflow-hidden rounded-[20px] bg-abyss p-10 lg:flex">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center rounded-full border border-graphite px-3 py-1 font-mono text-[13px] tracking-[-0.02em] text-graphite">
          01 / 04
        </span>
        <span className="font-mono text-[13px] tracking-[-0.02em] text-graphite">
          CICLO DO RECURSO PÚBLICO
        </span>
      </div>

      <div className="py-16">
        <p className="max-w-md text-[42px] leading-[1.1] tracking-[-0.02em] text-paper">
          Captar, receber, executar, prestar contas.
        </p>
        <p className="mt-8 max-w-sm text-[18px] leading-[1.3] tracking-[-0.001em] text-lichen/70">
          O território inteiro num só painel — curado por IA, com alertas no
          WhatsApp.
        </p>
      </div>

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
 * Shell das telas de autenticação, duas colunas.
 * - `image` (login): IMAGEM à esquerda + box do formulário à DIREITA.
 * - padrão (demais telas): formulário à esquerda + banda de bancada à direita.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
  image = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  image?: boolean;
}) {
  const form = (
    <div className="anim-page flex flex-col justify-between py-4 sm:px-6">
      <Link href="/" className="self-start">
        <BrandMark size="lg" />
      </Link>

      <div className="mx-auto w-full max-w-sm py-10">
        <div className={image ? "card p-8" : ""}>
          <h1 className="text-[36px] leading-[1.15] tracking-[-0.02em]">{title}</h1>
          {subtitle && (
            <p className="mt-3 text-sm leading-relaxed text-ink-2">{subtitle}</p>
          )}
          <div className="mt-10">{children}</div>
          {footer && <div className="mt-10 text-sm text-ink-2">{footer}</div>}
        </div>
      </div>

      <p className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
        © {new Date().getFullYear()} Hub Capture
      </p>
    </div>
  );

  return (
    <main className="grid min-h-screen grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-2">
      {image ? (
        <>
          <ImagePanel />
          {form}
        </>
      ) : (
        <>
          {form}
          <LabPanel />
        </>
      )}
    </main>
  );
}
