export type BadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-white/10 bg-white/5 text-gray-300",
  success: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
  warning: "border-amber-400/25 bg-amber-400/10 text-amber-300",
  danger: "border-red-400/25 bg-red-400/10 text-red-300",
  info: "border-sky-400/25 bg-sky-400/10 text-sky-300",
};

/** Badge de status semântico e colorido (PAGO, Crédito, Dedução, Emenda…). */
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium backdrop-blur-sm ${TONES[tone]}`}
    >
      <span className="glow-dot h-1.5 w-1.5" />
      {children}
    </span>
  );
}
