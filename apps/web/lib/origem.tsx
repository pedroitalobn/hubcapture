"use client";

/**
 * Origem do recurso — QUAIS fontes o usuário quer ver agora.
 *
 * Mesmo desenho do território (`lib/territorio.tsx`): a escolha vive na barra
 * de filtros do painel, ao lado do município, e vale para TODAS as lentes —
 * Meu painel (visão geral + feed), Captação e Recebidos. Seleção MULTI (marcar
 * TransfereGov e FNS vê os dois), vazio = todas. Persistida por navegador em
 * `localStorage`; opção que sair do perfil é podada na carga, como o território
 * poda IBGE fora do onboarding.
 *
 * O catálogo vem do PERFIL (`GET /profile` → `origens`), não de uma lista fixa
 * no front: o que o gestor marca é o GRUPO ("TransfereGov", "FNS") e a API é
 * quem sabe quais connectors cada grupo cobre. A lista fixa que existia aqui
 * oferecia fontes fora do recorte da v1 e reduzia o TransfereGov a UM dos seus
 * cinco connectors — marcar a origem filtrava por um id que quase nenhum
 * registro tinha, e a tela "não fazia nada".
 */

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useTerritorio } from "@/lib/territorio";

export interface Origem {
  chave: string;
  label: string;
  connectors?: string[];
}

const CHAVE = "hub_origem_recurso";

interface OrigemCtx {
  /** Catálogo do perfil: as origens que ESTE usuário pode filtrar. */
  origens: Origem[];
  /** chaves marcadas; vazio = todas as origens */
  selecionadas: string[];
  alternar: (chave: string) => void;
  todas: () => void;
}

const Ctx = createContext<OrigemCtx>({
  origens: [],
  selecionadas: [],
  alternar: () => {},
  todas: () => {},
});

function lerSalvas(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const bruto = window.localStorage.getItem(CHAVE);
    const lista = bruto ? (JSON.parse(bruto) as unknown) : [];
    return Array.isArray(lista) ? lista.map(String) : [];
  } catch {
    return []; // estado corrompido → volta para "todas"
  }
}

export function OrigemProvider({ children }: { children: React.ReactNode }) {
  const { perfil } = useTerritorio();
  const [selecionadas, setSelecionadas] = useState<string[]>(lerSalvas);

  const origens = useMemo<Origem[]>(() => perfil?.origens ?? [], [perfil]);

  // O perfil manda: origem que saiu do onboarding (ou do plano) sai do recorte
  // salvo — senão o painel ficaria filtrado por uma fonte que não existe mais.
  // Marcar TODAS uma a uma equivale a nenhum filtro.
  useEffect(() => {
    if (!origens.length) return;
    const validas = new Set(origens.map((o) => o.chave));
    setSelecionadas((prev) => {
      const limpo = prev.filter((c) => validas.has(c));
      const efetivo = limpo.length === origens.length ? [] : limpo;
      return efetivo.length === prev.length ? prev : efetivo;
    });
  }, [origens]);

  useEffect(() => {
    try {
      window.localStorage.setItem(CHAVE, JSON.stringify(selecionadas));
    } catch {
      /* sem persistência ainda funciona na sessão */
    }
  }, [selecionadas]);

  const valor = useMemo<OrigemCtx>(
    () => ({
      origens,
      selecionadas,
      alternar(chave: string) {
        setSelecionadas((atual) => {
          const novas = atual.includes(chave)
            ? atual.filter((x) => x !== chave)
            : [...atual, chave];
          return novas.length === origens.length ? [] : novas;
        });
      },
      todas: () => setSelecionadas([]),
    }),
    [origens, selecionadas],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useOrigem(): OrigemCtx {
  return useContext(Ctx);
}

/**
 * Valor do parâmetro `fonte` das chamadas de API: as origens escolhidas, ou
 * `undefined` quando são todas (aí a API não aplica recorte de origem).
 */
export function paramFonte(selecionadas: string[]): string[] | undefined {
  return selecionadas.length ? selecionadas : undefined;
}
