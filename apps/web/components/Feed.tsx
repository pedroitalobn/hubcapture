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

const NATUREZA_LABEL: Record<string, string> = {
  credito: "Crédito",
  deducao: "Dedução",
  repasse: "Repasse",
};

function naturezaTone(natureza: string): "success" | "danger" | "neutral" {
  if (natureza === "deducao") return "danger";
  if (natureza === "credito") return "success";
  return "neutral";
}

/** Feed de repasses agrupado por data, com subtotal "Pago no dia". */
export function Feed({ dias }: { dias: DiaGroup[] }) {
  return (
    <div className="flex flex-col gap-5">
      {dias.map((dia) => (
        <div key={dia.data}>
          <div className="mb-2 flex items-baseline justify-between gap-3 border-b border-line pb-1.5">
            <span className="font-semibold text-ink">{formatDate(dia.data)}</span>
            <span className="num text-sm text-muted">
              Pago no dia: {formatBRL(dia.subtotal)}
            </span>
          </div>
          <ul className="flex flex-col divide-y divide-line">
            {dia.itens.map((it) => (
              <li
                key={it.id}
                className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 text-sm"
              >
                <span className="flex min-w-0 flex-wrap items-center gap-2">
                  <StatusBadge tone={naturezaTone(it.natureza)}>
                    {NATUREZA_LABEL[it.natureza] ?? it.natureza}
                  </StatusBadge>
                  {it.emenda && <StatusBadge tone="info">emenda</StatusBadge>}
                  <span className="min-w-0 truncate text-ink-2">
                    <span className="font-medium uppercase text-ink">{it.fonte}</span>
                    {it.descricao ? ` · ${it.descricao}` : ""}
                    {it.categoria ? ` · ${it.categoria}` : ""}
                  </span>
                </span>
                <span
                  className={
                    it.natureza === "deducao"
                      ? "num shrink-0 font-medium text-danger"
                      : "num shrink-0 font-medium text-ink"
                  }
                >
                  {it.natureza === "deducao" ? "−" : ""}
                  {formatBRL(it.valor)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
