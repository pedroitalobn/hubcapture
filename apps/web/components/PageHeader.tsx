import type { ReactNode } from "react";
import { BotaoVoltar } from "./Voltar";

/**
 * Cabeçalho padrão das lentes do painel — mesma altura, mesmo ritmo (UI-07).
 * `voltar` é o retorno de tela: SEMPRE à esquerda, acima do título — nunca um
 * link pequeno no canto direito (lá ele some). `acoes` é o lugar das ações da
 * página (a primária vai de `.btn-primary`, com o glifo de `IconeAcao`).
 */
export function PageHeader({
  titulo,
  descricao,
  acoes,
  voltar,
}: {
  titulo: string;
  descricao?: ReactNode;
  acoes?: ReactNode;
  voltar?: { href: string; rotulo: string };
}) {
  return (
    <header className="anim-fade-up flex flex-col gap-2.5">
      {voltar && <BotaoVoltar href={voltar.href} rotulo={voltar.rotulo} />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="page-title text-ink">{titulo}</h1>
          {descricao && <p className="text-sm text-ink-2">{descricao}</p>}
        </div>
        {acoes && (
          <div className="flex flex-wrap items-center gap-2">{acoes}</div>
        )}
      </div>
    </header>
  );
}
