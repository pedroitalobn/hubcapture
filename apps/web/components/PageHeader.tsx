import type { ReactNode } from "react";

/** Cabeçalho padrão das lentes do painel — mesma altura, mesmo ritmo (UI-07). */
export function PageHeader({
  titulo,
  descricao,
  acoes,
}: {
  titulo: string;
  descricao?: string;
  acoes?: ReactNode;
}) {
  return (
    <header className="anim-fade-up flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="page-title text-ink">{titulo}</h1>
        {descricao && <p className="text-sm text-ink-2">{descricao}</p>}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </header>
  );
}
