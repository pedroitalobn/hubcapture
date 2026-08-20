import type { ReactNode } from "react";

/** Tons cheios da marca p/ KPIs que precisam contrastar com o canvas claro.
 *  `ink` usa os tokens de ação (inverte no tema escuro); lime/aqua/grad são
 *  preenchimentos fixos da marca com tinta abyss — legíveis nos dois temas. */
export type StatTone = "ink" | "lime" | "aqua" | "grad";

export interface StatCardProps {
  label: string;
  value: string;
  context?: string;
  icon?: ReactNode;
  tone?: StatTone;
}

/** KPI stat card flat: label mono em caixa-alta + valor grande em peso único. */
export function StatCard({ label, value, context, icon, tone }: StatCardProps) {
  return (
    <div className={`card card-hover p-5 ${tone ? `stat-${tone}` : ""}`}>
      <div className="flex items-center gap-2">
        {icon}
        <span className={`label-mono ${tone ? "text-inherit opacity-75" : ""}`}>
          {label}
        </span>
      </div>
      <div className="mt-3 text-[28px] leading-none tracking-[-0.02em] tabular-nums">
        {value}
      </div>
      {context && (
        <div
          className={`mt-2 font-mono text-[11px] tracking-[-0.02em] ${
            tone ? "text-inherit opacity-70" : "text-ink-3"
          }`}
        >
          {context}
        </div>
      )}
    </div>
  );
}
