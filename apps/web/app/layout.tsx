import type { Metadata, Viewport } from "next";
import { Archivo, Inter } from "next/font/google";
import "plyr/dist/plyr.css";
import "./globals.css";
import { UiVersionSync } from "@/components/UiVersionSync";

// Design system v1 (/previews/guia.html §3): Inter no corpo e na UI;
// Archivo nos títulos H1–H3 (caixa alta) e nos números. A Roboto Mono saiu
// do sistema — `--font-mono` no globals.css passa a apontar para a Inter.
const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans-src",
});
const display = Archivo({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display-src",
});

export const metadata: Metadata = {
  title: "Hub Capture",
  description: "Concentrador de propostas e repasses do governo brasileiro",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#08201e" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning: o script abaixo põe `data-theme` no <html>
    // antes da hidratação — sem isso o React acusaria mismatch do atributo.
    <html
      lang="pt-BR"
      className={`${sans.variable} ${display.variable}`}
      suppressHydrationWarning
    >
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
        {children}
      </body>
    </html>
  );
}
