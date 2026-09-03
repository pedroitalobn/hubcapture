"use client";

/**
 * Menu da conta — o rodapé do trilho lateral.
 *
 * Reúne o que não é LENTE sobre o território e por isso não merecia uma linha
 * na navegação: minha conta, ajustar perfil, administração, tema e sair. Antes
 * "Minha conta" disputava espaço com as lentes no meio da lista e o tema e o
 * "sair" ficavam soltos no fim do trilho — três controles de natureza
 * diferente empilhados sem nome. É a convenção que o gestor já conhece de
 * qualquer sistema: a identidade abre o que é da conta.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { IconeNav } from "@/components/icons";
import { cx } from "@/components/ui";

const PAPEL_LABEL: Record<string, string> = {
  parlamentar: "Parlamentar",
  executivo: "Executivo",
  equipe: "Equipe",
};

/** Iniciais para o avatar ("Pedro Bezerra" → "PB"; sem nome, o cifrão da marca). */
function iniciais(nome?: string | null): string {
  const partes = (nome ?? "").trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "•";
  const primeira = partes[0]![0] ?? "";
  const ultima = partes.length > 1 ? (partes[partes.length - 1]![0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}

export function MenuConta({
  nome,
  papel,
  municipios,
  admin,
  demo,
  onSair,
}: {
  nome?: string | null;
  papel?: string | null;
  municipios: number;
  admin: boolean;
  demo?: boolean;
  onSair: () => void;
}) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const fechar = useCallback(() => setAberto(false), []);

  useEffect(() => {
    if (!aberto) return;
    function fora(e: MouseEvent) {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    }
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);

  const contexto = [
    papel ? (PAPEL_LABEL[papel] ?? papel) : null,
    municipios > 0
      ? `${municipios} ${municipios === 1 ? "município" : "municípios"}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div ref={caixa} className="relative">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-haspopup="true"
        className="user-btn"
      >
        <span className="avatar" aria-hidden>
          {iniciais(nome)}
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-[13.5px] font-semibold">
            {nome || "Minha conta"}
          </b>
          {contexto && (
            <small className="block truncate text-[11.5px]">{contexto}</small>
          )}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cx("shrink-0 transition-transform", aberto && "rotate-180")}
          aria-hidden
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {aberto && (
        // abre PARA CIMA: o botão mora no rodapé do trilho
        <div className="menu anim-pop bottom-full left-0 right-0 mb-2">
          <Link href="/panel/account" className="menu-item" onClick={fechar}>
            <IconeNav nome="conta" />
            Minha conta
          </Link>
          {!demo && (
            <Link href="/onboarding" className="menu-item" onClick={fechar}>
              <IconeNav nome="painel" />
              Ajustar perfil
            </Link>
          )}
          {admin && (
            <Link href="/admin/users" className="menu-item" onClick={fechar}>
              <IconeNav nome="admin" />
              Administração
            </Link>
          )}
          <div className="menu-sep" />
          <p className="menu-sec">Aparência</p>
          <div className="px-2 pb-2">
            <ThemeToggle />
          </div>
          <div className="menu-sep" />
          <button type="button" onClick={onSair} className="menu-item">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="nav-icon" aria-hidden>
              <path d="M15 17l5-5-5-5" />
              <path d="M20 12H9" />
              <path d="M13 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h7" />
            </svg>
            Sair da conta
          </button>
        </div>
      )}
    </div>
  );
}
