"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

/** Alterna claro/escuro: grava a escolha e troca a classe .dark no <html>.
 * O estado inicial vem da classe já aplicada pelo script inline do layout. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function alternar() {
    const novo = !(dark ?? false);
    document.documentElement.classList.toggle("dark", novo);
    try {
      localStorage.setItem("hub_theme", novo ? "dark" : "light");
    } catch {
      /* storage indisponível — o tema ainda alterna nesta sessão */
    }
    setDark(novo);
  }

  return (
    <button
      onClick={alternar}
      title={dark ? "Mudar para tema claro" : "Mudar para tema escuro"}
      aria-label={dark ? "Mudar para tema claro" : "Mudar para tema escuro"}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-all duration-150 hover:bg-gray-100 hover:text-gray-900 active:scale-95 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100 ${className}`}
    >
      {/* null até montar (evita mismatch de hidratação); depois anima a troca */}
      {dark === null ? (
        <span className="h-4.5 w-4.5" />
      ) : dark ? (
        <Sun className="h-4.5 w-4.5 animate-scale-in" aria-hidden />
      ) : (
        <Moon className="h-4.5 w-4.5 animate-scale-in" aria-hidden />
      )}
    </button>
  );
}
