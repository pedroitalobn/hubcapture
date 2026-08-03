import type { ReactNode } from "react";
import { cx } from "./ui";

export type StatTone = "neutral" | "alerta" | "ok";

export interface StatCardProps {
  label: string;
  value: string;
  context?: ReactNode;
  tone?: StatTone;
  /** Valor por extenso quando o exibido é compacto (R$ 5,63 mi). */
  title?: string;
}

const TONES: Record<StatTone, { box: string; value: string; ctx: string }> = {
  neutral: { box: "border-line bg-bg", value: "text-ink", ctx: "text-muted" },
  alerta: { box: "border-warn-line bg-warn-bg", value: "text-warn", ctx: "text-warn" },
  ok: { box: "border-ok-line bg-ok-bg", value: "text-ok", ctx: "text-ok" },
};

/**
 * O corpo do valor acompanha o comprimento: "R$ 1.250.000,00" em 24px estoura
 * a coluna de um grid de 4 e o número aparecia cortado.
 */
function corpoDoValor(value: string): string {
  if (value.length <= 9) return "text-2xl";
  if (value.length <= 13) return "text-xl";
  return "text-lg";
}

/** KPI: rótulo pequeno em caixa-alta, valor grande tabular, linha de contexto. */
export function StatCard({ label, value, context, tone = "neutral", title }: StatCardProps) {
  const t = TONES[tone];
  return (
    <div className={cx("flex flex-col gap-1 rounded-xl border p-4 shadow-card", t.box)}>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        {label}
      </span>
      <span
        className={cx(
          "num font-bold tracking-tight text-pretty",
          corpoDoValor(value),
          t.value,
        )}
        title={title}
      >
        {value}
      </span>
      {context && <span className={cx("text-xs", t.ctx)}>{context}</span>}
    </div>
  );
}

/**
 * Faixa de KPIs. O grid acompanha a quantidade real de cartões — 2 cartões num
 * grid de 4 colunas deixava metade da faixa vazia (UI-09).
 */
export function StatRow({ children, cols }: { children: ReactNode; cols: number }) {
  const grid =
    cols <= 1
      ? "grid-cols-1"
      : cols === 2
        ? "grid-cols-2"
        : cols === 3
          ? "grid-cols-2 md:grid-cols-3"
          : "grid-cols-2 md:grid-cols-4";
  return <div className={cx("grid gap-3", grid)}>{children}</div>;
}
