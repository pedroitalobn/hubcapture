/**
 * Grupos de fonte — o vocabulário que o USUÁRIO fala (§30): TransfereGov e
 * FNS. Espelho de `services/fontes.py::GRUPOS` no backend: os connector ids
 * (`transferegov_ff`, `serpro`, `fns`…) são detalhe de ingestão e nunca
 * aparecem no filtro global. Ligar um grupo novo de volta = uma entrada aqui
 * e outra no registro do backend.
 */

export const GRUPOS_FONTE = [
  { chave: "transferegov", label: "TransfereGov" },
  { chave: "fns", label: "FNS" },
] as const;

export type GrupoFonte = (typeof GRUPOS_FONTE)[number]["chave"];

// connector id → grupo (espelho de services/fontes.py::grupo_de)
const GRUPO_POR_CONNECTOR: Record<string, GrupoFonte> = {
  transferegov_ff: "transferegov",
  transferegov_esp: "transferegov",
  transferegov_voluntarias: "transferegov",
  transferegov_disc: "transferegov",
  // o serpro coleta o painel da Visão Geral do TRANSFEREGOV — o SERPRO só hospeda
  serpro: "transferegov",
  fns: "fns",
};

/**
 * Grupo de um connector id; `null` para fonte fora do recorte atual (§30 —
 * fpm, emendas… podem existir no cache): com o filtro ativo ela não casa
 * com grupo nenhum, em vez de ser empurrada para um grupo errado.
 */
export function grupoDeFonte(fonte: string): GrupoFonte | null {
  return GRUPO_POR_CONNECTOR[fonte] ?? null;
}

/**
 * Valor do parâmetro `fonte` das chamadas de API: o grupo escolhido no filtro
 * global, ou `undefined` quando o usuário vê todas as fontes.
 */
export function paramFonte(fonteAtiva: string): string | undefined {
  return fonteAtiva || undefined;
}
