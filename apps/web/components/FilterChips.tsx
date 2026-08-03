"use client";

import { cx } from "./ui";

export interface ChipOption {
  value: string;
  label: string;
  count?: number;
}

/** Chips de filtro com contador. `todasLabel` some quando não faz sentido. */
export function FilterChips({
  options,
  selected,
  onSelect,
  todasLabel = "Todas",
  todasCount,
  ariaLabel,
}: {
  options: ChipOption[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  todasLabel?: string;
  todasCount?: number;
  ariaLabel?: string;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={ariaLabel}>
      <Chip
        active={selected === null}
        onClick={() => onSelect(null)}
        label={todasLabel}
        count={todasCount}
      />
      {options.map((o) => (
        <Chip
          key={o.value}
          active={selected === o.value}
          onClick={() => onSelect(selected === o.value ? null : o.value)}
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
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition",
        active
          ? "border-brand bg-brand font-medium text-brand-fg"
          : "border-line bg-bg text-ink-2 hover:border-line-strong hover:text-ink",
      )}
    >
      {label}
      {count !== undefined && (
        <span
          className={cx(
            "num rounded-full px-1.5 text-xs",
            active ? "bg-white/25 text-brand-fg" : "bg-surface-2 text-muted",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
