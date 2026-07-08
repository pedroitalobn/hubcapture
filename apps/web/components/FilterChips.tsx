"use client";

export interface ChipOption {
  value: string;
  label: string;
  count?: number;
}

/** Chips de filtro por fonte, cada um com contador de movimentações. */
export function FilterChips({
  options,
  selected,
  onSelect,
}: {
  options: ChipOption[];
  selected: string | null;
  onSelect: (value: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Chip active={selected === null} onClick={() => onSelect(null)} label="Todas" />
      {options.map((o) => (
        <Chip
          key={o.value}
          active={selected === o.value}
          onClick={() => onSelect(o.value)}
          label={o.label}
          count={o.count}
        />
      ))}
    </div>
  );
}

function Chip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition ${
        active
          ? "border-brand bg-brand text-brand-fg"
          : "border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
      }`}
    >
      {label}
      {count !== undefined && (
        <span
          className={`rounded-full px-1.5 text-xs ${
            active ? "bg-white/20" : "bg-gray-200 dark:bg-gray-800"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
