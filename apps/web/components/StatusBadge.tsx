import type { ReactNode } from "react";
import { cx } from "./ui";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-ink-2 border-line",
  success: "bg-ok-bg text-ok border-ok-line",
  warning: "bg-warn-bg text-warn border-warn-line",
  danger: "bg-danger-bg text-danger border-danger-line",
  info: "bg-info-bg text-info border-info-line",
  brand: "bg-brand-soft text-brand-soft-fg border-transparent",
};

/** Badge de status semântico (situação, natureza, fonte, pendência…). */
export function StatusBadge({
  children,
  tone = "neutral",
  mono = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  /** Para identificadores técnicos (slug da fonte, nº de processo). */
  mono?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        mono && "font-mono text-[11px] tracking-tight",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
