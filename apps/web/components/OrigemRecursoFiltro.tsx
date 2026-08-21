"use client";

/**
 * Filtro de ORIGEM DO RECURSO do trilho lateral — logo abaixo do território.
 *
 * Multi-select por chips (FNS + FPM juntos é escolha legítima); vazio = todas.
 * São só seis opções, então elas ficam à vista — popover esconderia um filtro
 * que o gestor usa o tempo todo na lente de recebidos.
 */

import { ORIGENS, useOrigem } from "@/lib/origem";

export function OrigemRecursoFiltro() {
  const { selecionadas, alternar, todas } = useOrigem();
  const tudo = selecionadas.length === 0;

  return (
    <div className="flex flex-wrap gap-1">
      <button
        type="button"
        onClick={todas}
        className={`chip ${tudo ? "chip-active" : ""}`}
        aria-pressed={tudo}
      >
        Todas
      </button>
      {ORIGENS.map((o) => {
        const ativa = selecionadas.includes(o.id);
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => alternar(o.id)}
            className={`chip ${ativa ? "chip-active" : ""}`}
            aria-pressed={ativa}
          >
            {o.rotulo}
          </button>
        );
      })}
    </div>
  );
}
