import type { ReactNode } from "react";

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: ReactNode;
}

/** KPI stat card: vidro spatial, label pequeno em caixa-alta + valor grande. */
export function StatCard({ label, value, context, icon }: StatCardProps) {
  return (
    <div className="card card-hover p-5">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">
          {label}
        </span>
      </div>
      <div className="text-display mt-2 text-[1.75rem] leading-none tabular-nums">
        {value}
      </div>
      {context && <div className="mt-2 text-xs text-ink-3">{context}</div>}
    </div>
  );
}
