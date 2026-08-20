"use client";

/**
 * Origem do recurso — QUAIS fontes de repasse o usuário quer ver agora.
 *
 * Mesmo desenho do território (`lib/territorio.tsx`): a escolha vive no
 * trilho lateral, logo abaixo dos municípios, e vale para as telas de
 * recebidos inteiras — seleção MULTI (marcar FNS e FPM vê os dois), vazio =
 * todas. Persistida por navegador em `localStorage`; opção que sair do
 * catálogo é podada na carga, como o território poda IBGE fora do perfil.
 */

import { createContext, useContext, useEffect, useMemo, useState } from "react";

/** Catálogo das origens de repasse (§13 — FONTES_REPASSE do backend). */
export const ORIGENS: { id: string; rotulo: string }[] = [
  { id: "fns", rotulo: "FNS" },
  { id: "fnde", rotulo: "FNDE" },
  { id: "fpm", rotulo: "FPM" },
  { id: "emendas", rotulo: "Emendas" },
  { id: "transferegov_ff", rotulo: "TransfereGov" },
  { id: "caixa", rotulo: "CAIXA" },
];

const CHAVE = "hub_origem_recurso";

interface OrigemCtx {
  /** ids marcados; vazio = todas as origens */
  selecionadas: string[];
  alternar: (id: string) => void;
  todas: () => void;
}

const Ctx = createContext<OrigemCtx>({
  selecionadas: [],
  alternar: () => {},
  todas: () => {},
});

export function OrigemProvider({ children }: { children: React.ReactNode }) {
  const [selecionadas, setSelecionadas] = useState<string[]>([]);

  useEffect(() => {
    try {
      const salvas = JSON.parse(localStorage.getItem(CHAVE) ?? "[]");
      if (Array.isArray(salvas)) {
        const validas = salvas.filter((s) => ORIGENS.some((o) => o.id === s));
        if (validas.length) setSelecionadas(validas);
      }
    } catch {
      /* localStorage indisponível/corrompido: começa em "todas" */
    }
  }, []);

  const valor = useMemo<OrigemCtx>(
    () => ({
      selecionadas,
      alternar(id: string) {
        setSelecionadas((atual) => {
          const novas = atual.includes(id)
            ? atual.filter((x) => x !== id)
            : [...atual, id];
          // marcar TODAS uma a uma = nenhum filtro; volta ao estado "todas"
          const efetivas = novas.length === ORIGENS.length ? [] : novas;
          try {
            localStorage.setItem(CHAVE, JSON.stringify(efetivas));
          } catch {
            /* sem persistência ainda funciona na sessão */
          }
          return efetivas;
        });
      },
      todas() {
        setSelecionadas([]);
        try {
          localStorage.setItem(CHAVE, "[]");
        } catch {
          /* idem */
        }
      },
    }),
    [selecionadas],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useOrigem(): OrigemCtx {
  return useContext(Ctx);
}
