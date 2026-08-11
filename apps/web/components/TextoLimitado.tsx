"use client";

/**
 * Texto com TETO de caracteres e "ver completo" em modal.
 *
 * Irmão do `TextoExpansivel`, para o caso em que ampliar in loco não serve: o
 * TÍTULO. As fontes não distinguem título de descrição — o `objeto` de uma
 * proposta do TransfereGov chega com o projeto inteiro (mais de 2 mil
 * caracteres) e é ele que encabeça o detalhe e a linha da lista. Recortado em
 * `linhas` de CSS, o título ainda ocupa meia tela; expandido no lugar, empurra
 * valor, empenho e prazo para fora da dobra. Aqui o corte é por caractere
 * (previsível em qualquer largura) e o texto completo vai para uma janela, que
 * é onde ele pode ocupar o espaço que precisa.
 *
 * O gatilho fica FORA do que `envolver` monta: nas listas o trecho vive dentro
 * de um `<Link>`, e botão dentro de âncora é HTML inválido (o clique disputaria
 * com a navegação — mesma razão do `copiavel={false}` do `NumeroProposta`).
 */

import { useState, type ReactNode } from "react";
import { Modal } from "./Modal";
import { recortarTexto } from "@/lib/format";
import { cx } from "./ui";

export function TextoLimitado({
  texto,
  limite = 160,
  titulo,
  rotulo,
  vazio = null,
  className,
  envolver,
}: {
  texto?: string | null;
  /** Teto de caracteres do trecho visível. */
  limite?: number;
  /** Título da janela ("Fortaleza/CE", "Objeto da proposta"…). */
  titulo: string;
  /** Etiqueta mono acima do título da janela. */
  rotulo?: string;
  /** O que mostrar quando a fonte não trouxe o texto. */
  vazio?: ReactNode;
  className?: string;
  /** Envolve o trecho recortado (ex.: o `<Link>` da linha da lista). */
  envolver?: (trecho: ReactNode) => ReactNode;
}) {
  const [aberto, setAberto] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const completo = String(texto ?? "").trim();
  const { trecho, cortado } = recortarTexto(completo, limite);

  if (!trecho) return <>{vazio}</>;

  async function copiar() {
    try {
      await navigator.clipboard.writeText(completo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* clipboard bloqueado — o texto segue selecionável na janela */
    }
  }

  return (
    <span className={cx("min-w-0", className)}>
      {envolver ? envolver(trecho) : trecho}
      {cortado && (
        <>
          {" "}
          <button
            type="button"
            onClick={(e) => {
              // o gatilho convive dentro de linhas clicáveis — o clique é dele
              e.preventDefault();
              e.stopPropagation();
              setAberto(true);
            }}
            title="Ver o texto completo"
            className="whitespace-nowrap align-baseline font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 underline decoration-hairline underline-offset-2 transition-colors hover:text-ink"
          >
            ver completo
          </button>
        </>
      )}
      <Modal
        aberto={aberto}
        aoFechar={() => setAberto(false)}
        titulo={titulo}
        rotulo={rotulo}
        rodape={
          <button
            type="button"
            onClick={() => void copiar()}
            className="btn btn-sm btn-ghost"
          >
            {copiado ? "✓ Copiado" : "Copiar texto"}
          </button>
        }
      >
        <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
          {completo}
        </p>
      </Modal>
    </span>
  );
}
