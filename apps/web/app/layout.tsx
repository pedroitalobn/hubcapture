import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hub Capture",
  description: "Concentrador de propostas e repasses do governo brasileiro",
};

/**
 * Aplica o tema salvo antes da primeira pintura. Sem isso, quem fixou "escuro"
 * vê um flash branco a cada navegação — o CSS só sabe do data-theme depois que
 * o React hidrata.
 */
const TEMA_INICIAL = `(function(){try{var t=localStorage.getItem("hub_tema");
if(t==="escuro")document.documentElement.setAttribute("data-theme","dark");
else if(t==="claro")document.documentElement.setAttribute("data-theme","light");}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: TEMA_INICIAL }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
