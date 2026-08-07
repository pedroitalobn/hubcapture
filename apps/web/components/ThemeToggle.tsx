"use client";

import { useEffect, useState } from "react";
import { cx } from "./ui";

type Tema = "sistema" | "claro" | "escuro";
const CHAVE = "hub_tema";

/** Aplica o tema no <html>; "sistema" remove o atributo e devolve à media query. */
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
    const salvo = window.localStorage.getItem(CHAVE) as Tema | null;
    if (salvo === "claro" || salvo === "escuro" || salvo === "sistema") setTema(salvo);
  }, []);

  function escolher(t: Tema) {
    setTema(t);
    window.localStorage.setItem(CHAVE, t);
    aplicarTema(t);
  }

  return (
    <div
      className="inline-flex rounded-md border border-line p-0.5"
      role="group"
      aria-label="Tema da interface"
    >
      {OPCOES.map((o) => (
        <button
          key={o.valor}
          type="button"
          onClick={() => escolher(o.valor)}
          title={o.titulo}
          aria-pressed={tema === o.valor}
          className={cx(
            "rounded px-2 py-1 text-xs transition",
            tema === o.valor
              ? "bg-brand font-medium text-brand-fg"
              : "text-muted hover:text-ink",
          )}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}
