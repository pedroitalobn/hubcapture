import type { ReactNode } from "react";

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: ReactNode;
}

/** KPI stat card flat: label mono em caixa-alta + valor grande em peso único. */
export function StatCard({ label, value, context, icon }: StatCardProps) {
  return (
    <div className="card card-hover p-5">
      <div className="flex items-center gap-2">
        {icon}
        <span className="label-mono">{label}</span>
      </div>
      <div className="mt-3 text-[28px] leading-none tracking-[-0.02em] tabular-nums">
        {value}
      </div>
      {context && (
        <div className="mt-2 font-mono text-[11px] tracking-[-0.02em] text-ink-3">
          {context}
        </div>
      )}
    </div>
  );
}
