import type { Metadata, Viewport } from "next";
import { MarcaProvider } from "@/lib/marca";
import { marcaDoHost } from "@/lib/marca-servidor";
import localFont from "next/font/local";
import "plyr/dist/plyr.css";
import "./globals.css";
import { UiVersionSync } from "@/components/UiVersionSync";

// Design system v1 (/previews/guia.html §3): Inter no corpo e na UI;
// Archivo nos títulos H1–H3 (caixa alta) e nos números. A Roboto Mono saiu
// do sistema — `--font-mono` no globals.css passa a apontar para a Inter.
//
// Fontes NO REPOSITÓRIO (app/fonts, subset latin do Google Fonts, licença
// OFL), não `next/font/google`: o Google baixava as fontes durante o BUILD,
// e o build quebrava quando a rede do servidor recebia uma resposta
// diferente ("Cannot read properties of null (reading '1')" no loader).
// Arquivo variável: um arquivo por família cobre todos os pesos.
const sans = localFont({
  src: "./fonts/inter-latin.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-sans-src",
});
const display = localFont({
  src: "./fonts/archivo-latin.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-display-src",
});

// White label (§69): título, ícone e cor da barra do navegador vêm da marca
// do HOST. A chamada é a mesma do layout (fetch deduplicado pelo Next).
export async function generateMetadata(): Promise<Metadata> {
  const marca = await marcaDoHost();
  return {
    title: marca.nome,
    description: marca.personalizada
      ? `${marca.nome} — propostas, repasses e oportunidades do seu município`
      : "Concentrador de propostas e repasses do governo brasileiro",
    icons: marca.icone_url ? { icon: marca.icone_url, apple: marca.icone_url } : undefined,
    applicationName: marca.nome,
  };
}

export async function generateViewport(): Promise<Viewport> {
  const marca = await marcaDoHost();
  return {
    themeColor: [
      { media: "(prefers-color-scheme: light)", color: marca.cor_tema_claro },
      { media: "(prefers-color-scheme: dark)", color: marca.cor_tema_escuro },
    ],
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const marca = await marcaDoHost();
  return (
    // suppressHydrationWarning: o script abaixo põe `data-theme` no <html>
    // antes da hidratação — sem isso o React acusaria mismatch do atributo.
    <html
      lang="pt-BR"
      className={`${sans.variable} ${display.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Fontes do catálogo da marca (Google Fonts, em runtime — o build
            continua sem rede, §67b). Só existe quando a marca escolheu uma. */}
        {marca.fontes_urls?.map((href) => (
          <link key={href} rel="stylesheet" href={href} />
        ))}
        {/* Tokens da marca: CSS montado no SERVIDOR a partir do tema validado
            (hex, catálogo, números) — nada digitado pelo dono vira código. Fica
            depois do globals.css e fora de @layer, então vence os padrões. */}
        {marca.css ? (
          <style id="marca-css" dangerouslySetInnerHTML={{ __html: marca.css }} />
        ) : null}
      </head>
      <body>
        {/* Aplica o tema salvo (ThemeToggle → localStorage `hub_tema`) e a
            versão de UI da plataforma (UiVersionSync → localStorage `hub_ui`)
            ANTES da primeira pintura, em todas as páginas — inline e síncrono
            de propósito: num efeito React o padrão piscaria primeiro. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              'try{var t=localStorage.getItem("hub_tema");if(t==="claro"||t==="escuro")document.documentElement.setAttribute("data-theme",t==="escuro"?"dark":"light");var u=localStorage.getItem("hub_ui");if(u==="v1")document.documentElement.setAttribute("data-ui","v1")}catch(e){}',
          }}
        />
        <UiVersionSync />
        <MarcaProvider marca={marca}>{children}</MarcaProvider>
      </body>
    </html>
  );
}
