import type { ReactNode } from "react";

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: ReactNode;
}

/** KPI stat card: label pequeno em caixa-alta + valor grande + linha de contexto. */
export function StatCard({ label, value, context, icon }: StatCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-800">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {label}
        </span>
      </div>
      <div className="mt-2 text-2xl font-bold">{value}</div>
      {context && <div className="mt-1 text-xs text-gray-500">{context}</div>}
    </div>
  );
}
