import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hub Capture",
  description: "Concentrador de propostas e repasses do governo brasileiro",
};

/* Aplica o tema antes do 1º paint (sem flash): escolha salva > preferência
 * do sistema. O toggle (ThemeToggle) grava em localStorage e alterna a classe. */
const THEME_INIT = `(function(){try{var t=localStorage.getItem("hub_theme");var d=t?t==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dark",d);}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
