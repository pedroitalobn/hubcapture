"use client";

import { useState } from "react";
import { cx } from "@/components/ui";

/* ────────────────────────────────────────── Nº da proposta em destaque ─────
   NR_PROPOSTA é a REFERÊNCIA da proposta (§35): é por ele que o gestor chama
   a proposta e é o que ele digita no portal da fonte para conferir. Estava
   diluído em linha de apoio cinza, do mesmo tamanho do órgão e da modalidade
   — quem varria a lista atrás de um número tinha que ler tudo. Aqui vira uma
   pílula com o acento da marca, sempre no mesmo lugar, e clicar copia (o
   passo seguinte do gestor é colar o número no portal ou no WhatsApp).

   Não confundir com `id_externo`/UUID: aqueles são plumbing da integração e
   continuam pequenos e cinzas no detalhe. Um identificador interno NUNCA
   entra aqui — a pílula é só para o número que a fonte publica. */

interface Props {
  /** NR_PROPOSTA vindo da fonte. Sem número, o componente não renderiza. */
  numero?: string | null;
  /** Termo da busca — realça o trecho casado dentro do número. */
  termo?: string;
  tamanho?: "sm" | "md";
  /**
   * Clicar copia. Passe `false` quando a pílula ficar DENTRO de um link: botão
   * aninhado em âncora é HTML inválido (interativo dentro de interativo) e o
   * clique disputaria com a navegação. Sem o botão o número segue selecionável.
   */
  copiavel?: boolean;
  className?: string;
}

const TAMANHOS = {
  sm: "px-1.5 py-px text-[11px]",
  md: "px-2 py-0.5 text-[13px]",
} as const;

/** Quebra o número em [antes, casado, depois] para realçar a busca. */
function partes(valor: string, termo?: string): [string, string, string] {
  const alvo = termo?.trim();
  if (!alvo) return [valor, "", ""];
  const i = valor.toLowerCase().indexOf(alvo.toLowerCase());
  if (i < 0) return [valor, "", ""];
  return [
    valor.slice(0, i),
    valor.slice(i, i + alvo.length),
    valor.slice(i + alvo.length),
  ];
}

export function NumeroProposta({
  numero,
  termo,
  tamanho = "md",
  copiavel = true,
  className,
}: Props) {
  const [copiado, setCopiado] = useState(false);
  const valor = (numero ?? "").trim();
  if (!valor) return null;

  async function copiar(e: React.MouseEvent) {
    // a pílula costuma viver DENTRO de um link para o detalhe: copiar não
    // pode navegar junto.
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(valor);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1600);
    } catch {
      /* clipboard bloqueado pelo navegador — o número segue legível na tela */
    }
  }

  const [antes, casado, depois] = partes(valor, termo);
  const classe = cx(
    "num inline-flex shrink-0 items-center gap-1.5 rounded-md border font-mono font-medium",
    "border-lime/40 bg-lime/10 text-ink",
    copiavel && "cursor-pointer transition-colors hover:bg-lime/20",
    TAMANHOS[tamanho],
    className,
  );
  const conteudo = (
    <>
      <span className="text-[0.85em] text-ink-3">Nº</span>
      <span className="select-all tracking-tight">
        {antes}
        {casado && <mark className="rounded-[2px] bg-lime px-px text-abyss">{casado}</mark>}
        {depois}
      </span>
      {copiado && <span className="tone-ok text-[0.85em]">copiado</span>}
    </>
  );

  if (!copiavel) {
    return (
      <span className={classe} title={`Nº da proposta ${valor}`}>
        {conteudo}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={copiar}
      title={copiado ? "Número copiado" : `Copiar o nº ${valor}`}
      aria-label={`Nº da proposta ${valor} — clique para copiar`}
      className={classe}
    >
      {conteudo}
    </button>
  );
}
