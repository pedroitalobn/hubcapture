import type { Metadata, Viewport } from "next";
import { Inter_Tight, Roboto_Mono } from "next/font/google";
import "plyr/dist/plyr.css";
import "./globals.css";

// Hierarquia tipográfica real: 400 no corpo, 500/600 em títulos e números —
// legibilidade primeiro; o tracking negativo continua dando o tom técnico.
const sans = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans-src",
});
const mono = Roboto_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-src",
});

export const metadata: Metadata = {
  title: "Hub Capture",
  description: "Concentrador de propostas e repasses do governo brasileiro",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#222f30" },
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
      className={`${sans.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <body>
        {/* Aplica o tema salvo (ThemeToggle → localStorage `hub_tema`) ANTES
            da primeira pintura, em todas as páginas — inline e síncrono de
            propósito: num efeito React o tema do sistema piscaria primeiro. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              'try{var t=localStorage.getItem("hub_tema");if(t==="claro"||t==="escuro")document.documentElement.setAttribute("data-theme",t==="escuro"?"dark":"light")}catch(e){}',
          }}
        />
        {children}
      </body>
    </html>
  );
}
