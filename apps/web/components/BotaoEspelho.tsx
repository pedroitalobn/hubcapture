"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { exportarEspelhoProposta } from "@/lib/api/client";
import { cx } from "@/components/ui";

/* ─────────────────────────────────────────── Atalho do espelho em PDF ─────
   Exportar a proposta era uma rota da API sem porta na interface. Aqui ela
   vira UM clique, disponível onde a proposta aparece: na linha da lista
   (ícone), no detalhe (botão) e em qualquer tela futura. No celular a ação
   abre a folha de compartilhamento com o PDF anexado; no desktop o arquivo é
   BAIXADO — o cliente perdia o download porque o Chrome de mesa com telefone
   vinculado também aceita `navigator.share` (ponto 12 do feedback). */

type Estado = "ocioso" | "gerando" | "pronto" | "erro";

const RESET_MS = 2600;

function Icone({ className }: { className?: string }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M12 18v-6" />
      <path d="m9.5 14.5 2.5-2.5 2.5 2.5" />
    </svg>
  );
}

export function BotaoEspelho({
  propostaId,
  /** `icone` cabe na célula de uma lista; `botao` no cabeçalho do detalhe. */
  formato = "botao",
  /** Tecla que dispara a exportação sem clique (só onde faz sentido: detalhe). */
  atalho,
  className,
  onResultado,
}: {
  propostaId: string;
  formato?: "botao" | "icone";
  atalho?: string;
  className?: string;
  onResultado?: (mensagem: string, tom: "ok" | "erro") => void;
}) {
  const [estado, setEstado] = useState<Estado>("ocioso");
  const emCurso = useRef(false);

  const exportar = useCallback(async () => {
    if (emCurso.current) return; // gerar duas vezes baixaria dois arquivos
    emCurso.current = true;
    setEstado("gerando");
    try {
      const r = await exportarEspelhoProposta(propostaId);
      setEstado("pronto");
      onResultado?.(
        r === "compartilhado"
          ? "Espelho pronto para compartilhar."
          : "Espelho em PDF baixado.",
        "ok",
      );
    } catch {
      setEstado("erro");
      onResultado?.("Não foi possível gerar o espelho em PDF.", "erro");
    } finally {
      emCurso.current = false;
      setTimeout(() => setEstado("ocioso"), RESET_MS);
    }
  }, [propostaId, onResultado]);

  // Atalho de teclado: ignorado enquanto o foco está num campo de texto (senão
  // digitar a letra no filtro dispararia um download).
  useEffect(() => {
    if (!atalho) return;
    function aoTeclar(e: KeyboardEvent) {
      if (e.key.toLowerCase() !== atalho!.toLowerCase()) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const alvo = e.target as HTMLElement | null;
      if (
        alvo?.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(alvo?.tagName ?? "")
      )
        return;
      e.preventDefault();
      void exportar();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [atalho, exportar]);

  const titulo =
    estado === "gerando"
      ? "Gerando o espelho…"
      : `Espelho em PDF — baixa no computador; no celular abre o compartilhamento${
          atalho ? ` (atalho: ${atalho.toUpperCase()})` : ""
        }`;

  if (formato === "icone") {
    return (
      <button
        type="button"
        onClick={() => void exportar()}
        disabled={estado === "gerando"}
        title={titulo}
        aria-label="Exportar espelho em PDF"
        className={cx(
          "icon-btn",
          estado === "erro" && "tone-danger",
          className,
        )}
      >
        {estado === "gerando" ? <span className="spinner" /> : <Icone />}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void exportar()}
      disabled={estado === "gerando"}
      title={titulo}
      // sólido: o formato "botao" só aparece no cabeçalho do registro, ao
      // lado das demais ações — ali o contorno do ghost não se lê como botão
      className={cx("btn btn-solid btn-sm", className)}
    >
      <Icone />
      {estado === "gerando"
        ? "Gerando…"
        : estado === "pronto"
          ? "Pronto ✓"
          : estado === "erro"
            ? "Erro"
            : "Espelho PDF"}
    </button>
  );
}
