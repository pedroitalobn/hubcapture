export type ProgressTone = "brand" | "success" | "warning" | "danger";

const TONES: Record<ProgressTone, string> = {
  brand: "bg-brand-600",
  success: "bg-green-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

/** Barra de progresso fina com preenchimento animado. */
export function ProgressBar({
  value,
  tone = "brand",
  className = "",
}: {
  value: number; // 0–100
  tone?: ProgressTone;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={`h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800 ${className}`}
    >
      <div
        className={`h-full rounded-full transition-[width] duration-700 ease-out ${TONES[tone]}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
