import type { LucideIcon } from "lucide-react";

export type StatTone = "brand" | "success" | "warning" | "danger" | "neutral";

const ICON_TONES: Record<StatTone, string> = {
  brand:
    "bg-brand-50 text-brand-700 ring-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:ring-brand-900/50",
  success:
    "bg-green-50 text-green-700 ring-green-100 dark:bg-green-900/30 dark:text-green-300 dark:ring-green-900/50",
  warning:
    "bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-900/50",
  danger:
    "bg-red-50 text-red-700 ring-red-100 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-900/50",
  neutral:
    "bg-gray-100 text-gray-600 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700",
};

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: LucideIcon;
  tone?: StatTone;
}

/** KPI stat card: ícone em chip colorido, valor grande, hover com elevação. */
export function StatCard({
  label,
  value,
  context,
  icon: Icon,
  tone = "brand",
}: StatCardProps) {
  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          {label}
        </span>
        {Icon && (
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 transition-transform duration-200 group-hover:scale-110 ${ICON_TONES[tone]}`}
          >
            <Icon className="h-4 w-4" aria-hidden />
          </span>
        )}
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums tracking-tight">
        {value}
      </div>
      {context && <div className="mt-1 text-xs text-gray-500">{context}</div>}
    </div>
  );
}
