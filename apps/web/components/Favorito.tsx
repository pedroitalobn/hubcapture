"use client";

import { useEffect, useRef, useState } from "react";
import { cx } from "@/components/ui";

/**
 * Estrela de favoritar — a ação mais repetida do painel e a que menos
 * respondia: era o glifo de texto ★/☆ trocando de cor, sem nenhum sinal de
 * que o clique pegou (a confirmação só chegava no re-render da lista).
 *
 * Aqui a estrela é um SVG que herda `currentColor` e ESTOURA no gesto: pop
 * com mola + anel radiando (classe `.fav-burst`, retirada por timeout). O
 * estado visual é OTIMISTA — vira na hora e o componente reverte se a API
 * recusar —, porque o custo de errar é uma estrela que volta, e o custo de
 * esperar é a UI parecer travada em toda linha da lista.
 *
 * Uma implementação só para busca, feed, Minhas Propostas e detalhe: antes
 * cada tela repetia o glifo com uma cor de hover diferente.
 */
export function Favorito({
  ativo,
  onToggle,
  rotuloOn = "Remover dos favoritos",
  rotuloOff = "Favoritar",
  comRotulo = false,
  tamanho = 18,
  className,
}: {
  ativo: boolean;
  /** Executa a troca; pode ser assíncrona (a estrela espera para reverter). */
  onToggle: () => void | Promise<unknown>;
  rotuloOn?: string;
  rotuloOff?: string;
  /** `true` mostra o texto ao lado (cabeçalho do detalhe). */
  comRotulo?: boolean;
  tamanho?: number;
  className?: string;
}) {
  const [estourando, setEstourando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  async function clicar() {
    if (ocupado) return;
    // o estouro só faz sentido ao LIGAR — desfavoritar é uma retirada
    if (!ativo) {
      setEstourando(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setEstourando(false), 600);
    }
    setOcupado(true);
    try {
      await onToggle();
    } finally {
      setOcupado(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void clicar()}
      aria-pressed={ativo}
      aria-label={ativo ? rotuloOn : rotuloOff}
      title={ativo ? rotuloOn : rotuloOff}
      className={cx(
        "fav",
        ativo && "fav-on",
        estourando && "fav-burst",
        comRotulo && "w-auto gap-1.5 px-2.5 font-mono text-[11px] uppercase tracking-[0.04em]",
        className,
      )}
    >
      <Estrela preenchida={ativo} tamanho={tamanho} />
      {comRotulo && <span>{ativo ? "Favorita" : "Favoritar"}</span>}
    </button>
  );
}

/** Estrela em `currentColor` — vazada quando desligada, cheia quando ligada. */
export function Estrela({
  preenchida,
  tamanho = 18,
}: {
  preenchida: boolean;
  tamanho?: number;
}) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="currentColor"
      fillOpacity={preenchida ? 1 : 0}
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3.2l2.72 5.51 6.08.89-4.4 4.29 1.04 6.06L12 17.09l-5.44 2.86 1.04-6.06-4.4-4.29 6.08-.89z" />
    </svg>
  );
}
