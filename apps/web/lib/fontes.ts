/**
 * Nome das fontes na TELA.
 *
 * `transferegov_disc` é id de integração; o gestor lê "TransfereGov —
 * Discricionárias" (§35: fonte de dados nunca vira identidade de registro, e
 * slug nunca vira rótulo). Espelho de `services/fontes.LABELS_CONNECTOR` no
 * backend — as respostas que já carregam `fonte_rotulo` devem usá-lo; este mapa
 * cobre as telas cujo payload traz só o id.
 */

const LABELS: Record<string, string> = {
  transferegov_ff: "TransfereGov — Fundo a Fundo",
  transferegov_esp: "TransfereGov — Especiais",
  transferegov_voluntarias: "TransfereGov — Voluntárias",
  transferegov_disc: "TransfereGov — Discricionárias",
  serpro: "TransfereGov — Visão Geral",
  fns: "FNS — Fundo Nacional de Saúde",
  fns_propostas: "FNS — Fundo Nacional de Saúde",
  fnde: "FNDE",
  fpm: "FPM — Fundo de Participação",
  emendas: "Emendas parlamentares",
  siconfi: "Siconfi/CAUC",
  sismob: "SISMOB",
  simec: "SIMEC",
  caixa: "CAIXA",
};

/** Connector id → nome legível da fonte (nunca o slug). */
export function rotuloFonte(fonte?: string | null): string {
  if (!fonte) return "";
  return LABELS[fonte] ?? fonte;
}
