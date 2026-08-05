export type BadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

/* Disciplina monocromática: o badge é sempre outline + mono; a semântica
   vem do dot de 6px (lime = ok; tons rebaixados p/ alerta/erro). */
const DOT: Record<BadgeTone, string> = {
  neutral: "bg-ink-3",
  success: "bg-ok",
  warning: "bg-warn",
  danger: "bg-danger",
  info: "bg-graphite",
};

/** Badge de status: pill hairline com dot semântico + label mono. */
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-[-0.02em] text-ink-2">
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[tone]}`} aria-hidden />
      {children}
    </span>
  );
}
