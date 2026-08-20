"use client";

/**
 * Fontes ativas — o recorte de FONTE do painel, irmão do de território.
 *
 * O usuário escolhe as fontes no onboarding; aqui ele decide quais DESSAS quer
 * ver naquele momento. A seleção é global (vale para todas as lentes do menu
 * profile-centric), persiste entre navegações/sessões e nunca amplia o que a
 * API mostra — é só um recorte de leitura sobre o que a coleta já gravou.
 *
 * O vocabulário é o do USUÁRIO: GRUPO ("transferegov", "fns"), não connector
 * id. Quem sabe que TransfereGov são cinco connectors é a API
 * (`services/fontes.py`), que expande na entrada — a tela nunca guarda essa
 * lista, senão ela envelheceria calada ao ligar/desligar uma fonte.
 *
 * `selecionadas` vazio = TODAS as fontes do perfil (o padrão). Isto NÃO é uma
 * aba por plataforma (§19): a navegação segue partindo do perfil, e a fonte
 * continua sendo detalhe de ingestão — aqui ela é só mais um recorte, como o
 * município.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useTerritorio } from "@/lib/territorio";

export interface GrupoFonte {
  chave: string;
  label: string;
  descricao?: string | null;
}

const CHAVE = "hub_fontes_ativas";

interface FontesCtx {
  /** Todos os grupos de fonte do perfil (o que o onboarding gravou). */
  grupos: GrupoFonte[];
  /** Recorte escolhido; vazio = todas. */
  selecionadas: string[];
  /** Grupos efetivamente em tela (o recorte, ou todos). */
  ativas: GrupoFonte[];
  alternar: (chave: string) => void;
  apenas: (chave: string) => void;
  todas: () => void;
}

const Ctx = createContext<FontesCtx | null>(null);

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

/** Esquece o recorte salvo (usado ao zerar o perfil, como o de território). */
export function limparFontesSalvas(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAVE);
}

export function FonteProvider({ children }: { children: React.ReactNode }) {
  // reusa o perfil que o TerritorioProvider já carregou — uma chamada só
  const { perfil } = useTerritorio();
  const [selecionadas, setSelecionadas] = useState<string[]>(lerSalvas);

  const grupos = useMemo(() => perfil?.fontes_grupos ?? [], [perfil]);

  // O perfil manda: fonte que saiu do onboarding (ou do plano) sai do recorte
  // salvo — senão o painel ficaria filtrado por uma fonte que não existe mais
  // e a tela viria vazia sem explicação.
  useEffect(() => {
    if (!perfil) return;
    const validas = new Set(grupos.map((g) => g.chave));
    setSelecionadas((prev) => {
      const limpo = prev.filter((c) => validas.has(c));
      return limpo.length === prev.length ? prev : limpo;
    });
  }, [perfil, grupos]);

  useEffect(() => {
    window.localStorage.setItem(CHAVE, JSON.stringify(selecionadas));
  }, [selecionadas]);

  const valor = useMemo<FontesCtx>(() => {
    const escolhidas = new Set(selecionadas);
    return {
      grupos,
      selecionadas,
      ativas: escolhidas.size ? grupos.filter((g) => escolhidas.has(g.chave)) : grupos,
      alternar: (chave) =>
        setSelecionadas((prev) =>
          prev.includes(chave) ? prev.filter((c) => c !== chave) : [...prev, chave],
        ),
      apenas: (chave) => setSelecionadas([chave]),
      todas: () => setSelecionadas([]),
    };
  }, [grupos, selecionadas]);

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useFontes(): FontesCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useFontes precisa do <FonteProvider>");
  return ctx;
}

/**
 * Valor do parâmetro `fonte` das chamadas de API: os grupos escolhidos, ou
 * `undefined` quando são todas (aí a API não recorta nada).
 */
export function paramFonte(selecionadas: string[]): string[] | undefined {
  return selecionadas.length ? selecionadas : undefined;
}

/** Nome de exibição de uma fonte a partir da chave do grupo. */
export function rotuloFonte(grupos: GrupoFonte[], chave: string): string {
  return grupos.find((g) => g.chave === chave)?.label ?? chave;
}
