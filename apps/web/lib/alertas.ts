export interface Alerta {
  id: string;
  proposta_id: string;
  tipo?: string | null;
  payload?: Record<string, unknown> | null;
  lido: boolean;
  created_at: string;
}

export const ALERTA_TIPO_LABEL: Record<string, string> = {
  status: "Mudança de situação",
  prazo: "Prazo",
  pendencia: "Pendência",
};

export function alertaTipoLabel(tipo?: string | null): string {
  return ALERTA_TIPO_LABEL[tipo ?? ""] ?? tipo ?? "Alerta";
}

/**
 * `payload` guarda o antes/depois da detecção de mudança (jobs/detect_changes).
 * O formato varia por tipo de alerta, então a frase é montada defensivamente.
 */
export function descreverAlerta(a: Alerta): string {
  const p = a.payload ?? {};
  const antes = p.antes ?? p.de ?? p.anterior;
  const depois = p.depois ?? p.para ?? p.atual;
  if (antes !== undefined && depois !== undefined) {
    return `${String(antes) || "—"} → ${String(depois) || "—"}`;
  }
  if (typeof p.descricao === "string") return p.descricao;
  if (typeof p.mensagem === "string") return p.mensagem;
  return "Mudança detectada na proposta";
}
