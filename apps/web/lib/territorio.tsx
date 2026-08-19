"use client";

/**
 * Território ativo — o recorte de município do painel.
 *
 * O usuário escolhe N municípios no onboarding; aqui ele decide quais DESSES
 * quer ver naquele momento. A seleção é global (vale para todas as lentes do
 * menu profile-centric: captação, recebidos, conformidade, obras, copiloto),
 * persiste entre navegações/sessões e nunca amplia o que a API mostra — o RLS
 * segue sendo o limite; isto é só um recorte de leitura.
 *
 * `selecionados` vazio = TODOS os municípios do perfil (o padrão).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api } from "@/lib/api/client";

export interface MunicipioPerfil {
  ibge: string;
  nome?: string | null;
  uf?: string | null;
  modo?: string;
}

export interface Perfil {
  nome?: string | null;
  papel?: string | null;
  municipios: MunicipioPerfil[];
  areas: string[];
  fontes?: string[];
  modulos?: string[];
}

const CHAVE = "hub_territorio_ativo";
const CHAVE_FONTE = "hub_fonte_ativa";

interface TerritorioCtx {
  perfil: Perfil | null;
  carregando: boolean;
  /** Todos os municípios do perfil (o que o onboarding gravou). */
  municipios: MunicipioPerfil[];
  /** Recorte escolhido; vazio = todos. */
  selecionados: string[];
  /** Municípios efetivamente em tela (o recorte, ou todos). */
  ativos: MunicipioPerfil[];
  /** Recorte global de FONTE (grupo "transferegov" | "fns"); vazio = todas. */
  fonteAtiva: string;
  alternar: (ibge: string) => void;
  apenas: (ibge: string) => void;
  todos: () => void;
  definirFonte: (grupo: string) => void;
  recarregar: () => Promise<void>;
}

const Ctx = createContext<TerritorioCtx | null>(null);

function lerSalvos(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const bruto = window.localStorage.getItem(CHAVE);
    const lista = bruto ? (JSON.parse(bruto) as unknown) : [];
    return Array.isArray(lista) ? lista.map(String) : [];
  } catch {
    return []; // estado corrompido → volta para "todos"
  }
}

function lerFonteSalva(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(CHAVE_FONTE) ?? "";
}

/** Esquece o recorte salvo (usado ao zerar o perfil: o território deixa de existir). */
export function limparTerritorioSalvo(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CHAVE);
  window.localStorage.removeItem(CHAVE_FONTE);
}

export function TerritorioProvider({ children }: { children: React.ReactNode }) {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [selecionados, setSelecionados] = useState<string[]>(lerSalvos);
  const [fonteAtiva, setFonteAtiva] = useState<string>(lerFonteSalva);

  const recarregar = useCallback(async () => {
    const { data } = await api.GET("/api/v1/profile");
    if (data) setPerfil(data as Perfil);
    setCarregando(false);
  }, []);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  // O perfil manda: município removido do onboarding sai do recorte salvo
  // (senão o painel ficaria filtrado por um território que não existe mais).
  useEffect(() => {
    if (!perfil) return;
    const validos = new Set(perfil.municipios.map((m) => m.ibge));
    setSelecionados((prev) => {
      const limpo = prev.filter((ibge) => validos.has(ibge));
      return limpo.length === prev.length ? prev : limpo;
    });
  }, [perfil]);

  useEffect(() => {
    window.localStorage.setItem(CHAVE, JSON.stringify(selecionados));
  }, [selecionados]);

  useEffect(() => {
    window.localStorage.setItem(CHAVE_FONTE, fonteAtiva);
  }, [fonteAtiva]);

  const municipios = useMemo(() => perfil?.municipios ?? [], [perfil]);

  const valor = useMemo<TerritorioCtx>(() => {
    const escolhidos = new Set(selecionados);
    return {
      perfil,
      carregando,
      municipios,
      selecionados,
      ativos: escolhidos.size
        ? municipios.filter((m) => escolhidos.has(m.ibge))
        : municipios,
      fonteAtiva,
      alternar: (ibge) =>
        setSelecionados((prev) =>
          prev.includes(ibge) ? prev.filter((i) => i !== ibge) : [...prev, ibge],
        ),
      apenas: (ibge) => setSelecionados([ibge]),
      todos: () => setSelecionados([]),
      definirFonte: setFonteAtiva,
      recarregar,
    };
  }, [perfil, carregando, municipios, selecionados, fonteAtiva, recarregar]);

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useTerritorio(): TerritorioCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTerritorio precisa do <TerritorioProvider>");
  return ctx;
}

/**
 * Valor do parâmetro `municipio` das chamadas de API: a lista escolhida, ou
 * `undefined` quando é o território inteiro (aí a API usa o RLS puro).
 */
export function paramMunicipio(selecionados: string[]): string[] | undefined {
  return selecionados.length ? selecionados : undefined;
}

/** Rótulo curto de um município ("Russas/CE"). */
export function rotuloMunicipio(m: MunicipioPerfil): string {
  return `${m.nome ?? m.ibge}${m.uf ? `/${m.uf}` : ""}`;
}
