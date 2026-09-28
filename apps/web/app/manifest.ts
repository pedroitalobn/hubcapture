import type { MetadataRoute } from "next";

/**
 * Manifesto do app (§63). É o que permite "Adicionar à tela de início" — e, no
 * iPhone/iPad, é CONDIÇÃO para receber notificação push: o Safari só entrega
 * Web Push a site instalado como app (iOS 16.4+).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Hub Capture",
    short_name: "Hub Capture",
    description: "Propostas, repasses e oportunidades do seu município num só painel.",
    start_url: "/panel",
    display: "standalone",
    background_color: "#F3F7F5",
    theme_color: "#031918",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
