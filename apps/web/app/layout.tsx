import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hub Capture",
  description: "Concentrador de propostas e repasses do governo brasileiro",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className="dark">
      <body>
        {/* Camada fixa de fundo: auroras + grade, atrás de todo o app */}
        <div aria-hidden className="spatial-bg">
          <div className="aurora aurora-a" />
          <div className="aurora aurora-b" />
          <div className="aurora aurora-c" />
          <div className="spatial-grid" />
        </div>
        {children}
      </body>
    </html>
  );
}
