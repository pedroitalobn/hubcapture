"use client";

/**
 * Filtro global de FONTE do painel — vive no trilho lateral, logo abaixo do
 * filtro de município (TerritorioFiltro): o usuário escolhe de onde quer ver
 * os dados agora (TransfereGov | FNS), e o recorte vale para as telas de dado
 * (Meu painel, Captação, Recursos recebidos), como o território (§33).
 *
 * As fontes seguem sendo detalhe de ingestão (§19): isto é um FILTRO de
 * leitura — o usuário fala grupo, e o backend expande para os connector ids
 * (`services/fontes.expandir_filtro`). Nunca vira aba de navegação.
 */

import { cx } from "@/components/ui";
import { GRUPOS_FONTE } from "@/lib/fontes";
import { useTerritorio } from "@/lib/territorio";

function chip(ativo: boolean): string {
  return cx(
    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] transition-colors",
    ativo
      ? "border-ink-2 font-medium text-ink"
      : "border-hairline text-ink-2 hover:text-ink",
  );
}

export function FonteFiltro() {
  const { fonteAtiva, definirFonte } = useTerritorio();

  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Fonte dos dados">
      <button
        onClick={() => definirFonte("")}
        aria-pressed={!fonteAtiva}
        className={chip(!fonteAtiva)}
      >
        Todas
      </button>
      {GRUPOS_FONTE.map((g) => {
        const ativo = fonteAtiva === g.chave;
        return (
          <button
            key={g.chave}
            // clicar no grupo já ativo volta para "todas" — mesmo gesto de
            // remover um chip do recorte de território
            onClick={() => definirFonte(ativo ? "" : g.chave)}
            aria-pressed={ativo}
            className={chip(ativo)}
          >
            {ativo && <span aria-hidden>✓</span>}
            {g.label}
          </button>
        );
      })}
    </div>
  );
}
