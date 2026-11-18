import type { MetadataRoute } from "next";
import { marcaDoHost } from "@/lib/marca-servidor";

/**
 * Manifesto do app (§63). É o que permite "Adicionar à tela de início" — e, no
 * iPhone/iPad, é CONDIÇÃO para receber notificação push: o Safari só entrega
 * Web Push a site instalado como app (iOS 16.4+).
 *
 * White label (§69): nome, ícone e cores são os da marca do HOST — o app
 * instalado a partir de marca.hubcapture.com.br leva o nome da marca.
 */
export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const marca = await marcaDoHost();
  const icone = marca.icone_url
    ? // PNG ou SVG — o navegador lê o tipo da resposta (Content-Type)
      { src: marca.icone_url, sizes: "any", purpose: "any" as const }
    : { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" as const };
  return {
    name: marca.nome,
    short_name: marca.nome,
    description: "Propostas, repasses e oportunidades do seu município num só painel.",
    start_url: "/panel",
    display: "standalone",
    background_color: marca.cor_tema_claro,
    theme_color: marca.tema?.cores?.escuro ?? "#031918",
    icons: [icone],
  };
}
