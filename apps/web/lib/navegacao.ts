/**
 * De onde o gestor veio — e para onde o "voltar" o devolve (§61).
 *
 * Meu painel e Propostas são entidades INDEPENDENTES: o painel é a visão
 * geral do território, Propostas é o construtor de consultas. Abrir uma
 * proposta a partir do painel e ser devolvido ao construtor (com as abas,
 * os filtros e a lista de outra pessoa que o usuário não pediu) é sair de
 * uma tela e voltar noutra — foi o que a página de detalhe fazia, porque o
 * retorno era fixo em `/panel/funding`.
 *
 * A origem viaja no link como `?de=<chave>` e o detalhe a lê. Chave
 * desconhecida (link velho, colado à mão) cai no padrão em vez de virar um
 * beco: o retorno nunca some da tela.
 */

export type OrigemNavegacao = "panel" | "funding" | "my-proposals" | "alerts";

export const PARAM_ORIGEM = "de";
/** Aba do construtor de onde a proposta foi aberta (§61). */
export const PARAM_ABA = "view";

const ORIGENS: Record<OrigemNavegacao, { href: string; rotulo: string }> = {
  panel: { href: "/panel", rotulo: "Meu painel" },
  funding: { href: "/panel/funding", rotulo: "Propostas" },
  "my-proposals": { href: "/panel/my-proposals", rotulo: "Minhas propostas" },
  alerts: { href: "/panel/alerts", rotulo: "Alertas" },
};

/** Link para o detalhe de uma proposta CARIMBADO com a tela de origem. */
export function linkProposta(
  propostaId: string,
  origem: OrigemNavegacao,
  aba?: string | null,
): string {
  const qs = new URLSearchParams({ [PARAM_ORIGEM]: origem });
  if (origem === "funding" && aba) qs.set(PARAM_ABA, aba);
  return `/panel/funding/${propostaId}?${qs.toString()}`;
}

/** Carimba a origem num href que a API já montou (o feed do Meu painel). */
export function comOrigem(href: string, origem: OrigemNavegacao): string {
  if (!href.startsWith("/")) return href; // link externo segue intacto
  const [caminho, query = ""] = href.split("?");
  const qs = new URLSearchParams(query);
  qs.set(PARAM_ORIGEM, origem);
  return `${caminho}?${qs.toString()}`;
}

/**
 * Para onde volta quem está no detalhe. `padrao` cobre o link sem carimbo e
 * o caso em que a tela de origem não está mais disponível (módulo desligado).
 */
export function retorno(
  origem: string | null | undefined,
  aba: string | null | undefined,
  padrao: OrigemNavegacao,
): { href: string; rotulo: string } {
  const chave = (origem ?? "") as OrigemNavegacao;
  const destino = ORIGENS[chave] ?? ORIGENS[padrao];
  if (destino === ORIGENS.funding && aba) {
    return { ...destino, href: `${destino.href}?${PARAM_ABA}=${encodeURIComponent(aba)}` };
  }
  return destino;
}
