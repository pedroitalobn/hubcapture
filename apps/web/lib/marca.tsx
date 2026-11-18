"use client";

/**
 * Marca em uso no site (white label, §69).
 *
 * O layout raiz (servidor) resolve a marca pelo HOST, injeta o CSS dela antes da
 * primeira pintura e entrega o resto aqui: nome, logo, assistente e os textos da
 * tela de login. Componentes que mostram a identidade (BrandMark, AuthShell,
 * trilho, Copiloto) leem de `useMarca()` — nunca de um "Hub Capture" fixo.
 */

import { createContext, useContext, type ReactNode } from "react";
import type { components } from "@hub/api-client";

export type Branding = components["schemas"]["BrandingRead"];

export const MARCA_PADRAO: Branding = {
  personalizada: false,
  nome: "Hub Capture",
  assistente: "Copiloto",
  tema: {} as Branding["tema"],
  css: "",
  fontes_urls: [],
  cadastro_aberto: true,
  cor_tema_claro: "#f3f7f5",
  cor_tema_escuro: "#08201e",
};

const Ctx = createContext<Branding>(MARCA_PADRAO);

export function MarcaProvider({
  marca,
  children,
}: {
  marca: Branding;
  children: ReactNode;
}) {
  return <Ctx.Provider value={marca}>{children}</Ctx.Provider>;
}

export function useMarca(): Branding {
  return useContext(Ctx);
}
