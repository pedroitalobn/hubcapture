import { formatBRL, formatDate } from "@/lib/format";
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

/** Feed de repasses agrupado por data, com subtotal "Pago no dia". */
export function Feed({ dias }: { dias: DiaGroup[] }) {
  if (dias.length === 0) {
    return (
      <p className="text-gray-500">
        Nenhum repasse no cache para o período. Sincronize uma fonte acima.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {dias.map((dia) => (
        <div key={dia.data}>
          <div className="mb-2 flex items-baseline justify-between border-b border-gray-200 pb-1 dark:border-gray-800">
            <span className="font-semibold">{formatDate(dia.data)}</span>
            <span className="text-sm text-gray-500">
              Pago no dia: {formatBRL(dia.subtotal)}
            </span>
          </div>
          <ul className="flex flex-col gap-2">
            {dia.itens.map((it) => (
              <li key={it.id} className="flex items-center justify-between gap-4 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <StatusBadge tone={naturezaTone(it.natureza)}>
                    {it.natureza}
                  </StatusBadge>
                  {it.emenda && <StatusBadge tone="info">emenda</StatusBadge>}
                  <span className="truncate">
                    <span className="font-medium uppercase">{it.fonte}</span>
                    {it.descricao ? ` · ${it.descricao}` : ""}
                  </span>
                </div>
                <span className="shrink-0 tabular-nums">{formatBRL(it.valor)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
