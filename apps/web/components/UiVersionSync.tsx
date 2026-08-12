"use client";

import { useEffect } from "react";
import { API_ORIGIN } from "@/lib/api/client";

/**
 * Sincroniza a versão de UI escolhida pelo admin (flag `ui_versao` no
 * /admin/config). A rota é pública e está fora do client tipado → fetch cru.
 *
 * O valor fica em localStorage (`hub_ui`) e é aplicado pré-paint pelo boot
 * script do layout raiz (sem flash na navegação seguinte); aqui a plataforma
 * é consultada a cada carga e o `data-ui` do <html> é ajustado ao vivo se o
 * admin mudou a flag. `data-ui="v1"` liga a camada v1 do globals.css.
 */
export function UiVersionSync() {
  useEffect(() => {
    void (async () => {
      try {
        // cache: no-store — a troca no painel precisa valer na carga seguinte,
        // não quando o cache heurístico do navegador resolver expirar
        const resp = await fetch(`${API_ORIGIN}/api/v1/ui`, { cache: "no-store" });
        if (!resp.ok) return;
        const { versao } = (await resp.json()) as { versao?: string };
        const v1 = versao === "v1";
        localStorage.setItem("hub_ui", v1 ? "v1" : "v2");
        if (v1) document.documentElement.setAttribute("data-ui", "v1");
        else document.documentElement.removeAttribute("data-ui");
      } catch {
        /* API fora do ar — mantém a última versão conhecida (localStorage) */
      }
    })();
  }, []);
  return null;
}
