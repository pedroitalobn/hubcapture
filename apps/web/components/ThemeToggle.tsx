"use client";

import { useEffect, useState } from "react";
import { cx } from "./ui";

type Tema = "sistema" | "claro" | "escuro";
const CHAVE = "hub_tema";

/** Aplica o tema no <html>; "sistema" remove o atributo e devolve à media query.
    O CSS lê `data-theme` (globals.css, "Tema em TRÊS estados") e o boot script
    do layout raiz reaplica a escolha salva antes da primeira pintura. */
export function aplicarTema(tema: Tema): void {
  const el = document.documentElement;
  if (tema === "sistema") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", tema === "escuro" ? "dark" : "light");
}

const OPCOES: { valor: Tema; rotulo: string; titulo: string }[] = [
  { valor: "claro", rotulo: "Claro", titulo: "Tema claro" },
  { valor: "escuro", rotulo: "Escuro", titulo: "Tema escuro" },
  { valor: "sistema", rotulo: "Auto", titulo: "Acompanhar o sistema" },
];

export function ThemeToggle() {
  const [tema, setTema] = useState<Tema>("sistema");

  useEffect(() => {
    try {
      const salvo = window.localStorage.getItem(CHAVE) as Tema | null;
      if (salvo === "claro" || salvo === "escuro" || salvo === "sistema")
        setTema(salvo);
    } catch {
      /* storage bloqueado → segue no sistema */
    }
  }, []);

  function escolher(t: Tema) {
    setTema(t);
    try {
      window.localStorage.setItem(CHAVE, t);
    } catch {
      /* sem storage a escolha vale só nesta sessão */
    }
    aplicarTema(t);
  }

  return (
    <div className="segmented" role="group" aria-label="Tema da interface">
      {OPCOES.map((o) => (
        <button
          key={o.valor}
          type="button"
          onClick={() => escolher(o.valor)}
          title={o.titulo}
          aria-pressed={tema === o.valor}
          className={cx(
            "segmented-item",
            tema === o.valor && "segmented-item-active",
          )}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}
