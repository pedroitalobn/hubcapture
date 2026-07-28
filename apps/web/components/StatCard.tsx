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
    <div className="glass-card glass-hover animate-fade-up p-5">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-widest text-gray-500">
          {label}
        </span>
      </div>
      <div className="text-gradient mt-2 text-2xl font-bold tabular-nums">
        {value}
      </div>
      {context && <div className="mt-1 text-xs text-gray-500">{context}</div>}
    </div>
  );
}
