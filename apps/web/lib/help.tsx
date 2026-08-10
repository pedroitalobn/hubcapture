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
 * Fonte de vídeo, analisada a partir da URL. O player (Plyr) decide o modo:
 * - `youtube`/`vimeo` → Plyr com o provider de embed nativo;
 * - `iframe` → players que já vêm prontos no embed (Bunny Stream
 *   `iframe.mediadelivery.net`, ou qualquer URL de /embed/ desconhecida);
 * - `arquivo` → mp4/webm direto (ou upload do admin) no Plyr html5 — é o
 *   modo com picture-in-picture.
 */
export type FonteVideo =
  | { modo: "youtube"; id: string }
  | { modo: "vimeo"; id: string }
  | { modo: "iframe"; src: string }
  | { modo: "arquivo"; src: string };

export function analisarVideo(url: string): FonteVideo {
  const yt = /(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/)([\w-]{6,})/.exec(
    url,
  );
  if (yt) return { modo: "youtube", id: yt[1]! };
  const vimeo = /vimeo\.com\/(?:video\/)?(\d+)/.exec(url);
  if (vimeo) return { modo: "vimeo", id: vimeo[1]! };
  // Bunny Stream: o link de embed já carrega o player completo do Bunny
  if (/(?:iframe\.mediadelivery\.net|video\.bunnycdn\.com)\//.test(url)) {
    return { modo: "iframe", src: url };
  }
  // arquivo direto (mp4/webm/ogg/m4v) → Plyr html5
  if (/\.(mp4|webm|ogv|ogg|m4v|mov)(\?|#|$)/i.test(url)) {
    return { modo: "arquivo", src: url };
  }
  // URL de embed de outra fonte → iframe genérico; resto tenta como arquivo
  if (/\/embed\//.test(url)) return { modo: "iframe", src: url };
  return { modo: "arquivo", src: url };
}
