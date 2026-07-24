export type BadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-3 text-ink-2",
  success:
    "bg-green-500/15 text-green-700 dark:bg-green-400/15 dark:text-green-300",
  warning: "bg-brand/20 text-brand-deep dark:bg-brand/15 dark:text-brand",
  danger: "bg-red-500/15 text-red-700 dark:bg-red-400/15 dark:text-red-300",
  info: "bg-blue-500/15 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
};

/** Badge de status semântico (PAGO, Crédito, Dedução, Emenda…). */
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}
