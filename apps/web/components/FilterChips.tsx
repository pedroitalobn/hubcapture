"use client";

import type { LucideIcon } from "lucide-react";

export interface ChipOption {
  value: string;
  label: string;
  count?: number;
  icon?: LucideIcon;
}

/** Chips de filtro (fonte, situação…), com contador e estado ativo destacado. */
export function FilterChips({
  options,
  selected,
  onSelect,
  allLabel = "Todas",
}: {
  options: ChipOption[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  allLabel?: string;
}) {
  return (
    <div className="flex flex-wrap gap-2 animate-fade-in">
      <Chip active={selected === null} onClick={() => onSelect(null)} label={allLabel} />
      {options.map((o) => (
        <Chip
          key={o.value}
          active={selected === o.value}
          onClick={() => onSelect(o.value)}
          label={o.label}
          count={o.count}
          icon={o.icon}
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
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count?: number;
  icon?: LucideIcon;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-all duration-150 active:scale-95 ${
        active
          ? "border-brand bg-brand text-brand-fg shadow-sm"
          : "border-gray-300 bg-white text-gray-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-brand-700 dark:hover:bg-brand-900/20 dark:hover:text-brand-300"
      }`}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
      {label}
      {count !== undefined && (
        <span
          className={`rounded-full px-1.5 py-px text-xs tabular-nums ${
            active
              ? "bg-white/20"
              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
