"use client";

/**
 * Filtro de território do painel — quais dos municípios do perfil o usuário
 * quer ver AGORA. Vive no trilho lateral (junto do território), então vale
 * para todas as telas: trocar aqui refaz captação, recebidos, conformidade,
 * obras e o Copiloto no mesmo recorte.
 *
 * Com um município só não há o que escolher: mostra o nome e pronto.
 */

import { useEffect, useRef, useState } from "react";
import { cx } from "@/components/ui";
import { rotuloMunicipio, useTerritorio } from "@/lib/territorio";

/** A partir daqui a lista ganha campo de busca (gabinete com muitos municípios). */
const COM_BUSCA = 8;

export function TerritorioFiltro() {
  const { municipios, selecionados, ativos, alternar, apenas, todos } = useTerritorio();
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const caixa = useRef<HTMLDivElement>(null);

  // fecha ao clicar fora / no Esc — o painel é flutuante dentro do trilho
  useEffect(() => {
    if (!aberto) return;
    function fora(e: MouseEvent) {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    }
    function esc(e: KeyboardEvent) {
      if (e.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  const [primeiro] = municipios;
  if (!primeiro) {
    return <p className="text-ink-2">Nenhum município — configure o onboarding</p>;
  }
  if (municipios.length === 1) {
    return <p className="text-ink-2">{rotuloMunicipio(primeiro)}</p>;
  }

  const tudo = selecionados.length === 0;
  const [unico] = ativos;
  const resumo = tudo
    ? `Todos os ${municipios.length} municípios`
    : ativos.length === 1 && unico
      ? rotuloMunicipio(unico)
      : `${ativos.length} de ${municipios.length} municípios`;

  const lista = busca.trim()
    ? municipios.filter((m) =>
        rotuloMunicipio(m).toLowerCase().includes(busca.trim().toLowerCase()),
      )
    : municipios;

  return (
    <div ref={caixa} className="relative">
      <button
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-haspopup="listbox"
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-hairline px-2.5 py-1.5 text-left text-sm text-ink-2 transition-colors hover:border-ink-2 hover:text-ink"
      >
        <span className="truncate">{resumo}</span>
        <span aria-hidden className="text-[10px] text-ink-3">
          {aberto ? "▲" : "▼"}
        </span>
      </button>

      {aberto && (
        <div
          role="listbox"
          aria-label="Municípios do painel"
          className="anim-pop absolute left-0 right-0 z-30 mt-1.5 rounded-xl border border-hairline bg-surface-2 p-2 shadow-lg"
        >
          {municipios.length >= COM_BUSCA && (
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="filtrar município"
              className="input mb-2 w-full text-sm"
              autoFocus
            />
          )}

          <button
            onClick={() => {
              todos();
              setAberto(false);
            }}
            className={cx(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-3",
              tudo && "font-medium text-ink",
            )}
          >
            <span aria-hidden className="w-3 text-center">
              {tudo ? "✓" : ""}
            </span>
            Todos os municípios
          </button>

          <div className="my-1 border-t border-hairline" />

          <div className="max-h-72 overflow-y-auto">
            {lista.map((m) => {
              const marcado = !tudo && selecionados.includes(m.ibge);
              return (
                <div key={m.ibge} className="group flex items-center gap-1">
                  <button
                    onClick={() => alternar(m.ibge)}
                    role="option"
                    aria-selected={marcado}
                    className={cx(
                      "flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-3",
                      marcado ? "text-ink" : "text-ink-2",
                    )}
                  >
                    <span aria-hidden className="w-3 text-center">
                      {marcado ? "✓" : ""}
                    </span>
                    <span className="truncate">{rotuloMunicipio(m)}</span>
                  </button>
                  {/* atalho do caso mais comum: olhar UM município de uma vez */}
                  <button
                    onClick={() => {
                      apenas(m.ibge);
                      setAberto(false);
                    }}
                    title={`Ver só ${rotuloMunicipio(m)}`}
                    className="shrink-0 px-1.5 py-1 font-mono text-[10px] uppercase tracking-[0.04em] text-ink-3 opacity-0 transition-opacity hover:text-ink group-hover:opacity-100 focus:opacity-100"
                  >
                    só este
                  </button>
                </div>
              );
            })}
            {lista.length === 0 && (
              <p className="px-2 py-1.5 text-sm text-ink-3">Nenhum município com esse nome.</p>
            )}
          </div>
        </div>
      )}

      {/* recorte ativo em chips — some quando é o território inteiro */}
      {!tudo && (
        <div className="mt-2 flex flex-wrap gap-1">
          {ativos.map((m) => (
            <button
              key={m.ibge}
              onClick={() => alternar(m.ibge)}
              title="Remover do recorte"
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 font-mono text-[11px] text-ink-2 hover:text-ink"
            >
              {rotuloMunicipio(m)}
              <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
