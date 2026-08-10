"use client";

/**
 * Class — o mapa de HINTS do painel.
 *
 * O provider busca `/help/hints` UMA vez (chave do elemento de UI → artigo
 * publicado) e todo `<Hint chave="..."/>` espalhado pelas telas consulta o
 * mapa localmente: com hint ativo, desenha o ícone ⓘ; sem hint (ou com o
 * módulo `ajuda` desligado — a rota responde 404), simplesmente não aparece
 * nada. Plantar ajuda num campo novo é responsabilidade do admin, não de
 * deploy: o front só precisa ter o <Hint/> no lugar.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api, API_ORIGIN, garantirSessao } from "@/lib/api/client";

export interface HintInfo {
  chave: string;
  artigo_slug: string;
  titulo: string;
  resumo?: string | null;
}

interface HelpCtx {
  /** chave → hint. Vazio enquanto carrega ou se o módulo está desligado. */
  hints: Map<string, HintInfo>;
  recarregar: () => Promise<void>;
}

const Ctx = createContext<HelpCtx | null>(null);

export function HelpProvider({ children }: { children: React.ReactNode }) {
  const [hints, setHints] = useState<Map<string, HintInfo>>(new Map());

  const recarregar = useCallback(async () => {
    // 404 (módulo desligado) ou erro de rede → mapa vazio → nenhum ícone.
    const { data, error } = await api.GET("/api/v1/class/hints");
    if (error || !data) return;
    setHints(new Map((data as HintInfo[]).map((h) => [h.chave, h])));
  }, []);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const valor = useMemo<HelpCtx>(() => ({ hints, recarregar }), [hints, recarregar]);
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

/** Hint da chave, ou null (sem provider montado também degrada para null). */
export function useHint(chave: string): HintInfo | null {
  const ctx = useContext(Ctx);
  return ctx?.hints.get(chave) ?? null;
}

/**
 * Mídia enviada pelo admin é servida autenticada (`/help/media/{id}` exige o
 * Bearer) — e tag <video>/<a download> não manda header. A saída é buscar o
 * blob com fetch autenticado e tocar/baixar via object URL. Quem chama é
 * responsável por revogar a URL (URL.revokeObjectURL) ao desmontar.
 */
export async function urlDaMidia(id: string): Promise<string> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/class/media/${id}`, {
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error("Não foi possível carregar a mídia");
  return URL.createObjectURL(await resp.blob());
}

/** Baixa um documento anexo com o nome original. */
export async function baixarMidia(id: string, nome: string): Promise<void> {
  const url = await urlDaMidia(id);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * URL de embed para vídeo externo. YouTube/Vimeo viram iframe; mp4 (ou
 * qualquer URL de arquivo) toca em <video> nativo — este helper devolve null
 * nesse caso, sinalizando "usa a tag de vídeo".
 */
export function urlDeEmbed(url: string): string | null {
  const yt = /(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([\w-]{6,})/.exec(url);
  if (yt) return `https://www.youtube.com/embed/${yt[1]}`;
  const vimeo = /vimeo\.com\/(?:video\/)?(\d+)/.exec(url);
  if (vimeo) return `https://player.vimeo.com/video/${vimeo[1]}`;
  return null;
}
