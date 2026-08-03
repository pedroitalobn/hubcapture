"use client";

import { cx } from "./ui";

export type RangePreset = "1d" | "7d" | "30d" | "90d";

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "1d", label: "1 dia" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "90d", label: "90 dias" },
];

/** Retorna a data de início (ISO) para um preset, relativa a hoje. */
export function presetToInicio(preset: RangePreset): string {
  const dias = preset === "1d" ? 1 : preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const d = new Date();
  d.setDate(d.getDate() - dias);
  return d.toISOString().slice(0, 10);
}

export function DateRangePresets({
  value,
  onChange,
}: {
  value: RangePreset;
  onChange: (p: RangePreset) => void;
}) {
  return (
    <div
      className="inline-flex overflow-hidden rounded-md border border-line"
      role="group"
      aria-label="Período"
    >
      {PRESETS.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => onChange(p.value)}
          aria-pressed={value === p.value}
          className={cx(
            "px-3 py-1.5 text-sm transition",
            value === p.value
              ? "bg-brand font-medium text-brand-fg"
              : "bg-bg text-ink-2 hover:bg-surface hover:text-ink",
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
