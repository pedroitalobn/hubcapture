import {
  Banknote,
  CalendarDays,
  Coins,
  HandCoins,
  Landmark,
  type LucideIcon,
} from "lucide-react";
import { formatBRL, formatDate } from "@/lib/format";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";

interface RepasseItem {
  id: string;
  fonte: string;
  descricao?: string | null;
  categoria?: string | null;
  natureza: string;
  valor?: string | null;
  emenda: boolean;
}

interface DiaGroup {
  data: string;
  subtotal: string;
  itens: RepasseItem[];
}

function naturezaTone(natureza: string): "success" | "danger" | "neutral" {
  if (natureza === "deducao") return "danger";
  if (natureza === "credito") return "success";
  return "neutral";
}

const FONTE_ICON: Record<string, LucideIcon> = {
  fpm: Landmark,
  emendas: HandCoins,
  fns: Coins,
  fnde: Coins,
  transferegov_ff: Landmark,
  caixa: Banknote,
};

/** Feed de repasses agrupado por data (timeline), com subtotal "Pago no dia". */
export function Feed({ dias }: { dias: DiaGroup[] }) {
  if (dias.length === 0) {
    return (
      <EmptyState
        icon={Banknote}
        title="Nenhum repasse no período"
        description="Não há repasses no cache para o período selecionado. Sincronize uma fonte acima para trazer os dados mais recentes."
      />
    );
  }
  return (
    <div className="flex flex-col gap-5 stagger">
      {dias.map((dia) => (
        <section
          key={dia.data}
          className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card dark:border-gray-800 dark:bg-gray-900"
        >
          <div className="flex items-center justify-between gap-3 border-b border-gray-100 bg-gray-50/70 px-4 py-2.5 dark:border-gray-800 dark:bg-gray-950/40">
            <span className="inline-flex items-center gap-2 text-sm font-semibold">
              <CalendarDays className="h-4 w-4 text-gray-400" aria-hidden />
              {formatDate(dia.data)}
            </span>
            <span className="text-xs font-medium text-gray-500">
              Pago no dia{" "}
              <span className="ml-1 rounded-md bg-green-50 px-2 py-0.5 font-semibold tabular-nums text-green-700 dark:bg-green-900/40 dark:text-green-300">
                {formatBRL(dia.subtotal)}
              </span>
            </span>
          </div>
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {dia.itens.map((it) => {
              const Icon = FONTE_ICON[it.fonte] ?? Banknote;
              return (
                <li
                  key={it.id}
                  className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate">
                        <span className="font-semibold uppercase">{it.fonte}</span>
                        {it.descricao ? (
                          <span className="text-gray-600 dark:text-gray-400">
                            {" "}
                            · {it.descricao}
                          </span>
                        ) : null}
                      </p>
                      <div className="mt-0.5 flex items-center gap-1.5">
                        <StatusBadge tone={naturezaTone(it.natureza)}>
                          {it.natureza}
                        </StatusBadge>
                        {it.emenda && <StatusBadge tone="info">emenda</StatusBadge>}
                      </div>
                    </div>
                  </div>
                  <span className="shrink-0 font-semibold tabular-nums">
                    {formatBRL(it.valor)}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
