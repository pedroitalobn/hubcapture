"use client";

/**
 * Modal — a janela sobreposta do app.
 *
 * Existia popover (`Hint`) e expansão in loco (`TextoExpansivel`), mas nenhum
 * lugar para mostrar um conteúdo INTEIRO sem empurrar a página: o objeto de uma
 * proposta do TransfereGov passa de 2 mil caracteres e, impresso no cabeçalho,
 * vira uma parede de texto antes de qualquer dado útil (valor, empenho, prazo).
 *
 * Renderiza em portal no `body` — dentro da árvore, o `overflow` das tabelas de
 * captação recortaria a janela e o `z-index` do trilho lateral passaria por
 * cima. Fecha no Esc e no clique fora, prende o Tab enquanto está aberto e
 * devolve o foco a quem abriu.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cx } from "./ui";

const FOCAVEIS =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

export function Modal({
  aberto,
  aoFechar,
  titulo,
  rotulo,
  rodape,
  children,
  className,
}: {
  aberto: boolean;
  aoFechar: () => void;
  /** Título visível da janela — também é o nome acessível. */
  titulo: string;
  /** Etiqueta mono acima do título (contexto: "Objeto da proposta"). */
  rotulo?: string;
  rodape?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const painel = useRef<HTMLDivElement>(null);
  const focoAnterior = useRef<HTMLElement | null>(null);
  // portal só depois da montagem: no SSR não existe `document`
  const [montado, setMontado] = useState(false);
  useEffect(() => setMontado(true), []);

  const aoTeclar = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        aoFechar();
        return;
      }
      if (e.key !== "Tab" || !painel.current) return;
      // prende o Tab: sem isto o foco escapa para a página atrás da janela
      const alvos = Array.from(
        painel.current.querySelectorAll<HTMLElement>(FOCAVEIS),
      ).filter((el) => el.offsetParent !== null);
      const primeiro = alvos[0];
      const ultimo = alvos[alvos.length - 1];
      if (!primeiro || !ultimo) return;
      const ativo = document.activeElement;
      if (e.shiftKey && (ativo === primeiro || ativo === painel.current)) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && ativo === ultimo) {
        e.preventDefault();
        primeiro.focus();
      }
    },
    [aoFechar],
  );

  useEffect(() => {
    if (!aberto) return;
    focoAnterior.current = document.activeElement as HTMLElement | null;
    // trava o scroll do fundo — rolar a página atrás da janela desorienta
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", aoTeclar, true);
    painel.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", aoTeclar, true);
      focoAnterior.current?.focus?.();
    };
  }, [aberto, aoTeclar]);

  if (!aberto || !montado) return null;

  return createPortal(
    <div
      className="anim-fade-in fixed inset-0 z-[100] flex items-end justify-center overflow-y-auto bg-abyss/45 p-0 backdrop-blur-[2px] sm:items-center sm:p-6"
      onMouseDown={(e) => {
        // só o clique no FUNDO fecha: arrastar uma seleção de texto de dentro
        // para fora não pode fechar a janela no meio da cópia
        if (e.target === e.currentTarget) aoFechar();
      }}
    >
      <div
        ref={painel}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        tabIndex={-1}
        className={cx(
          // `bg-card` sobrepõe o vidro translúcido do `.card`: sobre o fundo
          // escurecido, o texto atrás vazaria para dentro da janela
          "card anim-pop flex max-h-[88vh] w-full max-w-2xl flex-col gap-0 overflow-hidden rounded-b-none bg-card p-0 shadow-2xl outline-none sm:rounded-b-2xl",
          className,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            {rotulo && <span className="label-mono block">{rotulo}</span>}
            <h2 className="mt-0.5 text-base font-semibold leading-snug text-ink">
              {titulo}
            </h2>
          </div>
          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar"
            className="btn btn-sm btn-ghost shrink-0"
          >
            ✕
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {rodape && (
          <footer className="flex items-center justify-end gap-2 border-t border-hairline px-5 py-3">
            {rodape}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
