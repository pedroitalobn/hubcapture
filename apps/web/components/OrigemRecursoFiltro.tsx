"use client";

/**
 * Filtro de ORIGEM DO RECURSO do trilho lateral — logo abaixo do território.
 *
 * Multi-select por chips (TransfereGov + FNS juntos é escolha legítima); vazio
 * = todas. O catálogo vem do PERFIL — são as origens que o onboarding gravou —,
 * então o gestor nunca vê aqui uma fonte que o painel dele não tem. São poucas
 * opções: ficam à vista, sem popover.
 *
 * Com UMA origem só, o filtro não filtra nada e o componente não se desenha —
 * chip que não muda a tela lê como controle quebrado.
 */

import { useOrigem } from "@/lib/origem";

export function OrigemRecursoFiltro() {
  const { origens, selecionadas, alternar, todas } = useOrigem();
  const tudo = selecionadas.length === 0;

  if (origens.length < 2) return null;

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
      {origens.map((o) => {
        const ativa = selecionadas.includes(o.chave);
        return (
          <button
            key={o.chave}
            type="button"
            onClick={() => alternar(o.chave)}
            className={`chip ${ativa ? "chip-active" : ""}`}
            aria-pressed={ativa}
            // o label do grupo pode ser longo ("FNS — Fundo Nacional de
            // Saúde"); o chip mostra o nome curto e o título completo fica no
            // hover, para o trilho não virar duas linhas por origem
            title={o.label}
          >
            {rotuloCurto(o.label)}
          </button>
        );
      })}
    </div>
  );
}

/** Rótulo da seção — some junto com os chips quando não há o que filtrar. */
export function OrigemRecursoTitulo() {
  const { origens, selecionadas } = useOrigem();
  if (origens.length < 2) return null;
  return (
    <p className="label-mono mb-1.5 mt-4">
      Origem do recurso
      {selecionadas.length > 0 && (
        <span className="ml-1.5 normal-case text-ink-2">(filtrada)</span>
      )}
    </p>
  );
}

/** "FNS — Fundo Nacional de Saúde" → "FNS" (o travessão separa nome e glosa). */
function rotuloCurto(label: string): string {
  const [nome] = label.split("—");
  return nome?.trim() || label;
}
