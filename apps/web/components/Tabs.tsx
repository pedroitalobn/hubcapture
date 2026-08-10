"use client";

import type { LucideIcon } from "lucide-react";

export interface TabOption<T extends string = string> {
  value: T;
  label: string;
  icon?: LucideIcon;
}

/** Segmented control moderno: trilho neutro + aba ativa em "pill" elevado. */
export function Tabs<T extends string>({
  options,
  value,
  onChange,
}: {
  options: TabOption<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div
      role="tablist"
      className="inline-flex items-center gap-1 rounded-xl bg-gray-100 p-1 dark:bg-gray-900"
    >
      {options.map((o) => {
        const active = o.value === value;
        const Icon = o.icon;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 ${
              active
                ? "bg-white text-gray-900 shadow-sm ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:ring-gray-700"
                : "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            {Icon && (
              <Icon
                className={`h-4 w-4 transition-colors ${active ? "text-brand-600 dark:text-brand-400" : ""}`}
                aria-hidden
              />
            )}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
