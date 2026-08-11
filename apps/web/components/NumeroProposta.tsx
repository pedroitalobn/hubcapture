"use client";

import { useState } from "react";

interface Props {
  /** NR_PROPOSTA vindo da fonte. */
  numero?: string | null;
  /** Usado quando a fonte não publica o número separado do id externo. */
  fallback?: string | null;
  /** Termo pesquisado — realçado dentro do número. */
  termo?: string;
  size?: "sm" | "md" | "lg";
}

const SIZES: Record<NonNullable<Props["size"]>, string> = {
  sm: "px-1.5 py-0.5 text-xs",
  md: "px-2 py-1 text-sm",
  lg: "px-3 py-1.5 text-base",
};

/** Quebra o número em [antes, casado, depois] para realçar o trecho buscado. */
function partes(valor: string, termo?: string): [string, string, string] {
  const alvo = termo?.trim();
  if (!alvo) return [valor, "", ""];
  const i = valor.toLowerCase().indexOf(alvo.toLowerCase());
  if (i < 0) return [valor, "", ""];
  return [valor.slice(0, i), valor.slice(i, i + alvo.length), valor.slice(i + alvo.length)];
}

/**
 * Número da proposta (NR_PROPOSTA) em destaque — é por ele que o gestor
 * localiza a proposta nas fontes oficiais. Clicar copia para a área de
 * transferência.
 */
export function NumeroProposta({ numero, fallback, termo, size = "md" }: Props) {
  const [copiado, setCopiado] = useState(false);
  const valor = (numero ?? "").trim() || (fallback ?? "").trim();

  if (!valor) {
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">Nº não informado</span>
    );
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(valor);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1500);
    } catch {
      /* clipboard bloqueado pelo navegador — o número segue visível na tela */
    }
  }

  const [antes, casado, depois] = partes(valor, termo);

  return (
    <button
      type="button"
      onClick={copiar}
      title={copiado ? "Número copiado" : `Copiar o nº ${valor}`}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 font-mono font-semibold tracking-tight text-amber-900 transition hover:bg-amber-100 dark:border-amber-500/40 dark:bg-amber-400/10 dark:text-amber-200 dark:hover:bg-amber-400/20 ${SIZES[size]}`}
    >
      <span className="font-sans text-[0.65rem] uppercase opacity-70">Nº</span>
      <span>
        {antes}
        {casado && (
          <mark className="rounded-sm bg-amber-300 text-amber-950 dark:bg-amber-300 dark:text-amber-950">
            {casado}
          </mark>
        )}
        {depois}
      </span>
      <span className="font-sans text-[0.65rem] opacity-60">{copiado ? "✓" : "⧉"}</span>
    </button>
  );
}
