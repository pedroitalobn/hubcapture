import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ─────────────────────────────────────────────────────────────── Button ──
   Delega para as classes de `globals.css` (.btn/.btn-primary/…) em vez de
   montar a própria paleta. A versão anterior referenciava tokens que não
   existem no @theme (bg-bg, bg-brand-700, border-line-strong, text-danger…),
   e no Tailwind 4 utilitário desconhecido compila para NADA — o botão saía
   sem fundo e sem borda. Uma implementação só, igual em todas as telas. */

type Variante = "primary" | "secondary" | "ghost" | "accent" | "danger";
type Tamanho = "sm" | "md";

const VARIANTE: Record<Variante, string> = {
  primary: "btn-primary",
  secondary: "btn-ghost",
  ghost: "btn-ghost border-transparent",
  accent: "btn-accent",
  danger: "tone-danger-soft",
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
        "btn",
        VARIANTE[variante],
        tamanho === "sm" && "btn-sm",
        className,
      )}
    />
  );
}

/* ────────────────────────────────────────────────────────────── Input ──── */

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("input", className)} />;
}

/** Par rótulo/campo com o mesmo ritmo vertical em todo o app. */
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
    <label className={cx("field", className)}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

/** Par rótulo/valor somente-leitura — a unidade de exibição de dado. */
export function Dado({
  rotulo,
  valor,
  tom,
  destaque,
  className,
}: {
  /** Texto do rótulo — aceita nó para acomodar um <Hint/> ao lado. */
  rotulo: ReactNode;
  valor?: ReactNode;
  tom?: "ok" | "warn" | "danger";
  /** `true` sobe o valor um degrau na hierarquia (.value-lg). */
  destaque?: boolean;
  className?: string;
}) {
  const vazio = valor === null || valor === undefined || valor === "";
  return (
    <div className={cx("field", className)}>
      <span className="field-label">{rotulo}</span>
      <span
        className={cx(
          destaque ? "value-lg" : "field-value",
          tom === "ok" && "tone-ok",
          tom === "warn" && "tone-warn",
          tom === "danger" && "tone-danger",
          vazio && "text-ink-3",
        )}
      >
        {vazio ? "—" : valor}
      </span>
    </div>
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
  return <As className={cx("card", className)}>{children}</As>;
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
    info: "border-hairline text-ink-2",
    ok: "tone-ok-soft",
    erro: "tone-danger-soft",
  } as const;
  return (
    <p
      role="status"
      className={cx(
        "anim-pop rounded-lg border px-3 py-2 text-sm",
        tons[tom],
      )}
    >
      {children}
    </p>
  );
}
