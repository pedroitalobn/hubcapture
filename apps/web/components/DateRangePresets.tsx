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

/** Controle segmentado de período, em vidro (estilo visionOS). */
export function DateRangePresets({
  value,
  onChange,
}: {
  value: RangePreset;
  onChange: (p: RangePreset) => void;
}) {
  return (
    <div className="glass-card inline-flex gap-1 rounded-full! p-1">
      {PRESETS.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className={`pressable rounded-full px-3 py-1.5 text-sm transition ${
            value === p.value
              ? "bg-white/12 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,.12),0_2px_10px_rgba(99,102,241,.25)]"
              : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
