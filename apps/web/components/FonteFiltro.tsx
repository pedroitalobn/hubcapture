"use client";

/**
 * Seletor de FONTE do painel — quais das fontes do perfil o usuário quer ver
 * AGORA. Vive no trilho lateral, logo abaixo do território, porque é o mesmo
 * tipo de controle: um recorte global que refaz captação, recebidos e o Meu
 * painel de uma vez.
 *
 * Fala GRUPO ("TransfereGov"), não connector id — o usuário nunca precisou
 * saber que TransfereGov são cinco connectors. Com uma fonte só não há o que
 * escolher: mostra o nome e pronto.
 */

import { useEffect, useRef, useState } from "react";
import { cx } from "@/components/ui";
import { useFontes } from "@/lib/fontes";

export function FonteFiltro() {
  const { grupos, selecionadas, ativas, alternar, apenas, todas } = useFontes();
  const [aberto, setAberto] = useState(false);
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

  const [primeira] = grupos;
  if (!primeira) {
    return <p className="text-ink-2">Nenhuma fonte — configure o onboarding</p>;
  }
  if (grupos.length === 1) {
    return <p className="text-ink-2">{primeira.label}</p>;
  }

  const tudo = selecionadas.length === 0;
  const [unica] = ativas;
  const resumo = tudo
    ? `Todas as ${grupos.length} fontes`
    : ativas.length === 1 && unica
      ? unica.label
      : `${ativas.length} de ${grupos.length} fontes`;

  return (
    <div ref={caixa} className="relative">
      <button
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-haspopup="listbox"
        className="pressable flex w-full items-center justify-between gap-2 rounded-lg border border-hairline px-2.5 py-1.5 text-left text-sm text-ink-2 hover:border-ink-2 hover:text-ink"
      >
        <span className="truncate">{resumo}</span>
        <span aria-hidden className="text-[10px] text-ink-3">
          {aberto ? "▲" : "▼"}
        </span>
      </button>

      {aberto && (
        <div
          role="listbox"
          aria-label="Fontes do painel"
          className="anim-pop absolute left-0 right-0 z-30 mt-1.5 rounded-xl border border-hairline bg-surface-2 p-2 shadow-lg"
        >
          <button
            onClick={() => {
              todas();
              setAberto(false);
            }}
            className={cx(
              "pressable flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-3",
              tudo && "font-medium text-ink",
            )}
          >
            <span aria-hidden className="w-3 text-center">
              {tudo ? "✓" : ""}
            </span>
            Todas as fontes
          </button>

          <div className="my-1 border-t border-hairline" />

          {grupos.map((g) => {
            const marcada = !tudo && selecionadas.includes(g.chave);
            return (
              <div key={g.chave} className="group flex items-center gap-1">
                <button
                  onClick={() => alternar(g.chave)}
                  role="option"
                  aria-selected={marcada}
                  className={cx(
                    "pressable flex min-w-0 flex-1 items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-3",
                    marcada ? "text-ink" : "text-ink-2",
                  )}
                >
                  <span aria-hidden className="mt-0.5 w-3 shrink-0 text-center">
                    {marcada ? "✓" : ""}
                  </span>
                  <span className="min-w-0">
                    {/* o NOME da fonte quebra em vez de truncar: "FNS — Fundo
                        Naci…" esconde justamente a identidade que o usuário
                        veio procurar (a descrição abaixo é que pode ceder) */}
                    <span className="block">{g.label}</span>
                    {g.descricao && (
                      <span className="block text-[11px] text-ink-3">{g.descricao}</span>
                    )}
                  </span>
                </button>
                {/* atalho do caso mais comum: olhar UMA fonte de cada vez */}
                <button
                  onClick={() => {
                    apenas(g.chave);
                    setAberto(false);
                  }}
                  title={`Ver só ${g.label}`}
                  className="shrink-0 self-start px-1.5 py-1 font-mono text-[10px] uppercase tracking-[0.04em] text-ink-3 opacity-0 transition-opacity hover:text-ink group-hover:opacity-100 focus:opacity-100"
                >
                  só esta
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* recorte ativo em chips — some quando são todas as fontes */}
      {!tudo && (
        <div className="mt-2 flex flex-wrap gap-1">
          {ativas.map((g) => (
            <button
              key={g.chave}
              onClick={() => alternar(g.chave)}
              title="Remover do recorte"
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 font-mono text-[11px] text-ink-2 hover:text-ink"
            >
              {g.label}
              <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
