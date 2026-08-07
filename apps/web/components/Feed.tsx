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
      <p className="text-ink-3">
        Nenhum repasse no cache para o período. Sincronize uma fonte acima.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {dias.map((dia) => (
        <div key={dia.data} className="card p-5">
          <div className="mb-3 flex items-baseline justify-between border-b border-hairline pb-2.5">
            <span className="tracking-tight">{formatDate(dia.data)}</span>
            <span className="font-mono text-[12px] tracking-[-0.02em] text-ink-3">
              PAGO NO DIA{" "}
              <span className="tabular-nums text-ink">{formatBRL(dia.subtotal)}</span>
            </span>
          </div>
          <ul className="flex flex-col gap-2.5">
            {dia.itens.map((it) => (
              <li key={it.id} className="flex items-center justify-between gap-4 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <StatusBadge tone={naturezaTone(it.natureza)}>
                    {it.natureza}
                  </StatusBadge>
                  {it.emenda && <StatusBadge tone="info">emenda</StatusBadge>}
                  <span className="truncate text-ink-2">
                    <span className="font-mono text-[12px] uppercase tracking-[-0.02em] text-ink">
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
