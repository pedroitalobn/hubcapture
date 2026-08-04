import type { ReactNode } from "react";

/**
 * Vazio de verdade — distinto do carregando. A Captação dizia "Nenhuma proposta
 * no cache ainda" enquanto o fetch corria, o que era simplesmente falso (UI-06).
 */
export function EmptyState({
  titulo,
  descricao,
  acao,
}: {
  titulo: string;
  descricao?: string;
  acao?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-line-strong bg-surface px-6 py-8">
      <p className="font-medium text-ink">{titulo}</p>
      {descricao && <p className="max-w-prose text-sm text-muted">{descricao}</p>}
      {acao}
    </div>
  );
}
