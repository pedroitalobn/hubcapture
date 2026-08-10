"use client";

import { MapPin, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Button } from "./Button";

/** Formulário compartilhado de sincronização por município (IBGE, 7 dígitos). */
export function SyncMunicipioForm({
  onSync,
  loading,
  buttonLabel = "Buscar nas fontes",
  placeholder = "3550308",
}: {
  onSync: (ibge: string) => void | Promise<void>;
  loading: boolean;
  buttonLabel?: string;
  placeholder?: string;
}) {
  const [ibge, setIbge] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void onSync(ibge);
      }}
      className="flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-card animate-fade-up dark:border-gray-800 dark:bg-gray-900"
    >
      <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        Sincronizar município (IBGE, 7 dígitos)
        <span className="relative">
          <MapPin
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
            aria-hidden
          />
          <input
            value={ibge}
            onChange={(e) => setIbge(e.target.value.replace(/\D/g, ""))}
            placeholder={placeholder}
            maxLength={7}
            inputMode="numeric"
            className="rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 font-normal tabular-nums transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950"
          />
        </span>
      </label>
      <Button
        type="submit"
        loading={loading}
        disabled={ibge.length !== 7}
        icon={<RefreshCw className="h-4 w-4" aria-hidden />}
      >
        {loading ? "Sincronizando…" : buttonLabel}
      </Button>
    </form>
  );
}
