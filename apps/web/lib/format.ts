/** Formata um valor (string decimal vinda da API) em BRL. */
export function formatBRL(v?: string | number | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * BRL compacto para KPI (R$ 5,63 mi). Valores grandes em cartão pequeno não
 * cabem por extenso e a ordem de grandeza é o que importa na leitura rápida.
 */
export function formatBRLCompact(v?: string | number | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  const abs = Math.abs(n);
  const fmt = (x: number, suf: string) =>
    `R$ ${x.toLocaleString("pt-BR", { maximumFractionDigits: x < 10 ? 2 : 1 })} ${suf}`;
  if (abs >= 1_000_000_000) return fmt(n / 1_000_000_000, "bi");
  if (abs >= 1_000_000) return fmt(n / 1_000_000, "mi");
  if (abs >= 1_000) return fmt(n / 1_000, "mil");
  return formatBRL(n);
}

/** Formata uma data ISO (YYYY-MM-DD) em pt-BR. */
export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

/** Dia e mês, sem o ano — para prazos dentro do ano corrente. */
export function formatDayMonth(iso?: string | null): string {
  if (!iso) return "—";
  const [, m, d] = iso.slice(0, 10).split("-");
  if (!m || !d) return iso;
  return `${d}/${m}`;
}

/** Data + hora local (para "sincronizado em"). */
export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Meia-noite local de uma data ISO — evita erro de fuso ao comparar prazos. */
function midnight(iso: string): Date | null {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

/**
 * Dias inteiros até uma data (negativo = vencido). `null` se não der para
 * interpretar — quem chama decide o que mostrar nesse caso.
 */
export function diasAte(iso?: string | null, hoje = new Date()): number | null {
  if (!iso) return null;
  const alvo = midnight(iso);
  if (!alvo) return null;
  const base = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return Math.round((alvo.getTime() - base.getTime()) / 86_400_000);
}

/** "vence hoje" / "vence em 9 dias" / "vencido há 3 dias". */
export function prazoLabel(iso?: string | null, hoje = new Date()): string {
  const d = diasAte(iso, hoje);
  if (d === null) return "—";
  if (d === 0) return "vence hoje";
  if (d === 1) return "vence amanhã";
  if (d > 0) return `vence em ${d} dias`;
  if (d === -1) return "venceu ontem";
  return `vencido há ${Math.abs(d)} dias`;
}

/** Tempo relativo curto ("há 2 h", "há 3 d") para feeds de alerta. */
export function haQuantoTempo(iso?: string | null, agora = new Date()): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "—";
  const seg = Math.max(0, Math.round((agora.getTime() - dt.getTime()) / 1000));
  if (seg < 60) return "agora";
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86_400) return `há ${Math.floor(seg / 3600)} h`;
  const dias = Math.floor(seg / 86_400);
  if (dias < 30) return `há ${dias} d`;
  return formatDate(iso);
}
