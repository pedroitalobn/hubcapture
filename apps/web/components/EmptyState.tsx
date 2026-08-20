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
    <div className="anim-fade-up flex flex-col items-start gap-3 rounded-2xl border border-dashed border-hairline bg-[image:var(--wash)] px-6 py-8">
      <p className="text-display text-ink">{titulo}</p>
      {descricao && <p className="max-w-prose text-sm text-ink-2">{descricao}</p>}
      {acao}
    </div>
  );
}
