import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ─────────────────────────────────────────────────────────────── Button ── */

type Variante = "primary" | "secondary" | "ghost" | "danger";
type Tamanho = "sm" | "md";

const VARIANTE: Record<Variante, string> = {
  primary: "bg-brand text-brand-fg border-brand hover:bg-brand-700 hover:border-brand-700",
  secondary: "bg-bg text-ink-2 border-line-strong hover:bg-surface hover:text-ink",
  ghost: "bg-transparent text-ink-2 border-transparent hover:bg-surface hover:text-ink",
  danger: "bg-danger-bg text-danger border-danger-line hover:bg-danger hover:text-white",
};

const TAMANHO: Record<Tamanho, string> = {
  sm: "px-2.5 py-1 text-xs gap-1.5",
  md: "px-4 py-2 text-sm gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  tamanho?: Tamanho;
}

export function Button({
  variante = "primary",
  tamanho = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center rounded-md border font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTE[variante],
        TAMANHO[tamanho],
        className,
      )}
    />
  );
}

/* ────────────────────────────────────────────────────────────── Input ──── */

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cx(
        "rounded-md border border-line bg-bg px-3 py-2 text-sm text-ink",
        "placeholder:text-muted focus:border-brand focus:outline-none",
        className,
      )}
    />
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("flex flex-col gap-1.5 text-sm text-ink-2", className)}>
      <span className="font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

/* ─────────────────────────────────────────────────────────────── Card ──── */

export function Card({
  children,
  className,
  as: As = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
}) {
  return (
    <As className={cx("rounded-xl border border-line bg-bg shadow-card", className)}>
      {children}
    </As>
  );
}

/* ──────────────────────────────────────────────────────────── Mensagem ── */

/** Retorno de operação (sync, salvar). Nunca um alert() nem um texto solto. */
export function Aviso({
  tom = "info",
  children,
}: {
  tom?: "info" | "ok" | "erro";
  children: ReactNode;
}) {
  const tons = {
    info: "border-info-line bg-info-bg text-info",
    ok: "border-ok-line bg-ok-bg text-ok",
    erro: "border-danger-line bg-danger-bg text-danger",
  } as const;
  return (
    <p role="status" className={cx("rounded-md border px-3 py-2 text-sm", tons[tom])}>
      {children}
    </p>
  );
}
