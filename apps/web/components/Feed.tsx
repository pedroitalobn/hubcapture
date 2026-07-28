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
    <div className="flex flex-col gap-5">
      {dias.map((dia, i) => (
        <div
          key={dia.data}
          className={`glass-card animate-fade-up stagger-${(i % 6) + 1} p-5`}
        >
          <div className="mb-3 flex items-baseline justify-between border-b border-white/10 pb-2">
            <span className="font-semibold">{formatDate(dia.data)}</span>
            <span className="text-sm text-gray-400">
              Pago no dia:{" "}
              <span className="text-gradient font-semibold">
                {formatBRL(dia.subtotal)}
              </span>
            </span>
          </div>
          <ul className="flex flex-col">
            {dia.itens.map((it) => (
              <li
                key={it.id}
                className="-mx-2 flex items-center justify-between gap-4 rounded-lg px-2 py-1.5 text-sm transition hover:bg-white/5"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <StatusBadge tone={naturezaTone(it.natureza)}>
                    {it.natureza}
                  </StatusBadge>
                  {it.emenda && <StatusBadge tone="info">emenda</StatusBadge>}
                  <span className="truncate text-gray-300">
                    <span className="font-medium uppercase text-gray-100">
                      {it.fonte}
                    </span>
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
