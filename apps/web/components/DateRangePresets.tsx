"use client";

export type RangePreset = "1d" | "7d" | "30d";

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "1d", label: "Dia anterior" },
  { value: "7d", label: "Últimos 7 dias" },
  { value: "30d", label: "Últimos 30 dias" },
];

/** Retorna a data de início (ISO) para um preset, relativa a hoje. */
export function presetToInicio(preset: RangePreset): string {
  const d = new Date();
  const dias = preset === "1d" ? 1 : preset === "7d" ? 7 : 30;
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
    <div className="segmented">
      {PRESETS.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className={`segmented-item ${
            value === p.value ? "segmented-item-active" : ""
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
