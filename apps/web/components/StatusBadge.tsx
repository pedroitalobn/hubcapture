export type BadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

const TONES: Record<BadgeTone, { pill: string; dot: string }> = {
  neutral: {
    pill: "bg-gray-100 text-gray-700 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700",
    dot: "bg-gray-400",
  },
  success: {
    pill: "bg-green-50 text-green-700 ring-green-200 dark:bg-green-900/40 dark:text-green-300 dark:ring-green-900",
    dot: "bg-green-500",
  },
  warning: {
    pill: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900",
    dot: "bg-amber-500",
  },
  danger: {
    pill: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-900/40 dark:text-red-300 dark:ring-red-900",
    dot: "bg-red-500",
  },
  info: {
    pill: "bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:ring-blue-900",
    dot: "bg-blue-500",
  },
};

/** Badge de status com dot indicador (PAGO, Crédito, Em execução…). */
export function StatusBadge({
  children,
  tone = "neutral",
  pulse = false,
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  pulse?: boolean;
}) {
  const t = TONES[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${t.pill}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${t.dot} ${pulse ? "animate-pulse-dot" : ""}`}
        aria-hidden
      />
      {children}
    </span>
  );
}
