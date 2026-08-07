"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { cx } from "./ui";

/**
 * Texto longo com opção de AMPLIAR.
 *
 * Os registros das fontes trazem campos de extensão arbitrária — a `DESCRICAO`
 * de um programa do TransfereGov passa de 2 mil caracteres. Impresso inteiro
 * numa célula da grade, ele vira uma torre de texto que empurra os campos
 * vizinhos para fora da tela (era exatamente isso na tela de detalhe).
 *
 * Aqui o valor entra recortado em `linhas`; o botão só aparece quando há mesmo
 * corte (medido no DOM — nada de adivinhar por contagem de caracteres, que erra
 * com a largura da coluna). Ampliado, o texto ganha rolagem própria em vez de
 * esticar a página.
 */
export function TextoExpansivel({
  texto,
  linhas = 3,
  className,
  abertoInicial = false,
}: {
  texto: string;
  /** Linhas visíveis quando recolhido. */
  linhas?: number;
  className?: string;
  abertoInicial?: boolean;
}) {
  const [aberto, setAberto] = useState(abertoInicial);
  const [cortado, setCortado] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);

  // mede o corte real: com clamp aplicado, scrollHeight > clientHeight
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => setCortado(el.scrollHeight - el.clientHeight > 2);
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, [texto, linhas, aberto]);

  return (
    <div className={cx("flex flex-col items-start gap-1", className)}>
      <p
        ref={ref}
        className={cx(
          "field-value whitespace-pre-line",
          aberto
            ? "max-h-[24rem] overflow-y-auto pr-1"
            : "overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical]",
        )}
        style={aberto ? undefined : { WebkitLineClamp: linhas }}
      >
        {texto}
      </p>
      {(cortado || aberto) && (
        <button
          type="button"
          onClick={() => setAberto((v) => !v)}
          aria-expanded={aberto}
          className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 transition-colors hover:text-ink"
        >
          {aberto ? "Recolher ↑" : "Ampliar ↓"}
        </button>
      )}
    </div>
  );
}
