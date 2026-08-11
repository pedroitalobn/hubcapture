"use client";

export interface MultiChipOption {
  value: string;
  label: string;
  count?: number;
}

/**
 * Chips de filtro com seleção múltipla (irmão do `FilterChips`, que é de
 * escolha única). "Todos" = nenhum selecionado.
 */
export function MultiSelectChips({
  options,
  selected,
  onChange,
  allLabel = "Todos",
}: {
  options: MultiChipOption[];
  selected: string[];
  onChange: (values: string[]) => void;
  allLabel?: string;
}) {
  function alternar(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Chip
        active={selected.length === 0}
        onClick={() => onChange([])}
        label={allLabel}
      />
      {options.map((o) => (
        <Chip
          key={o.value}
          active={selected.includes(o.value)}
          onClick={() => alternar(o.value)}
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
      type="button"
      aria-pressed={active}
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
