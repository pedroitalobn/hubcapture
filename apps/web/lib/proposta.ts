import type { BadgeTone } from "@/components/StatusBadge";
import { diasAte } from "@/lib/format";

/**
 * Proposta como a API devolve (schemas/proposta.py::PropostaRead).
 * Os 23 campos estão aqui de propósito: a tela existe para mostrá-los, não
 * para escolher meia dúzia.
 */
export interface Proposta {
  id: string;
  fonte: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_ibge?: string | null;
  municipio_nome?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  contrapartida?: string | null;
  situacao?: string | null;
  emenda?: string | null;
  prazos?: Prazo[] | null;
  pendencias?: Pendencia[] | null;
  movimentacao?: string | null;
  data_atualizacao_fonte?: string | null;
  url_origem?: string | null;
  proveniencia?: Record<string, string> | null;
  resumo_ia?: string | null;
  cache_atualizado_em?: string | null;
}

export interface Prazo {
  tipo?: string | null;
  data_limite?: string | null;
}

export interface Pendencia {
  descricao?: string | null;
  prazo?: string | null;
}

export const FONTE_LABEL: Record<string, string> = {
  transferegov_ff: "TransfereGov · Fundo a Fundo",
  transferegov_esp: "TransfereGov · Especiais",
  transferegov_disc: "TransfereGov · Discricionárias",
  fns: "Fundo Nacional de Saúde",
  fnde: "FNDE",
  serpro: "SERPRO",
};

export const FONTE_CURTA: Record<string, string> = {
  transferegov_ff: "TransfereGov FF",
  transferegov_esp: "TransfereGov Esp",
  transferegov_disc: "TransfereGov Disc",
  fns: "FNS",
  fnde: "FNDE",
  serpro: "SERPRO",
};

export function fonteLabel(fonte: string): string {
  return FONTE_LABEL[fonte] ?? fonte;
}

export function fonteCurta(fonte: string): string {
  return FONTE_CURTA[fonte] ?? fonte;
}

/**
 * A situação vem como texto livre de cada fonte (não há enum no backend), então
 * a classificação é por palavra-chave — sempre com um neutro seguro no fim.
 */
export function situacaoTone(situacao?: string | null): BadgeTone {
  const s = (situacao ?? "").toLowerCase();
  if (!s) return "neutral";
  if (/(pend|irregular|bloquei|rejeit|indefer|cancel|inadimpl)/.test(s)) return "danger";
  if (/(anális|analis|aguard|tramit|diligên|diligen|complement|ajust)/.test(s)) return "warning";
  if (/(aprovad|celebrad|conclu|assinad|empenhad|pag|efetivad|regular)/.test(s)) return "success";
  return "info";
}

/**
 * O que exibir como título. Fontes por scraping (FNS) muitas vezes não mandam
 * `titulo`; cair para "—" descarta o `objeto`, que veio preenchido no mesmo
 * payload. A flag diz à UI que aquilo é o objeto, não o título oficial.
 */
export function tituloProposta(p: Proposta): { texto: string; ehFallback: boolean } {
  if (p.titulo?.trim()) return { texto: p.titulo, ehFallback: false };
  if (p.objeto?.trim()) return { texto: p.objeto, ehFallback: true };
  if (p.numero_proposta?.trim()) return { texto: `Proposta ${p.numero_proposta}`, ehFallback: true };
  return { texto: `Registro ${p.id_externo}`, ehFallback: true };
}

export function pendencias(p: Proposta): Pendencia[] {
  return (p.pendencias ?? []).filter((x) => x && (x.descricao || x.prazo));
}

export function prazos(p: Proposta): Prazo[] {
  return (p.prazos ?? []).filter((x) => x && x.data_limite);
}

/** Menor data-limite entre prazos e pendências — o relógio real da proposta. */
export function prazoMaisProximo(p: Proposta): { data: string; tipo: string } | null {
  const candidatos: { data: string; tipo: string }[] = [];
  for (const pr of prazos(p)) {
    if (pr.data_limite) candidatos.push({ data: pr.data_limite, tipo: pr.tipo ?? "prazo" });
  }
  for (const pe of pendencias(p)) {
    if (pe.prazo) candidatos.push({ data: pe.prazo, tipo: pe.descricao ?? "pendência" });
  }
  if (candidatos.length === 0) return null;
  return candidatos.sort((a, b) => a.data.localeCompare(b.data))[0]!;
}

/** Tom do cartão: pendência ou prazo curto puxam atenção; aprovado descansa. */
export function propostaTone(p: Proposta): BadgeTone {
  if (pendencias(p).length > 0) return "danger";
  const prox = prazoMaisProximo(p);
  const d = prox ? diasAte(prox.data) : null;
  if (d !== null && d <= 15) return "warning";
  return situacaoTone(p.situacao);
}

/**
 * Resume `proveniencia` ({campo: 'api'|'scrape'}) em uma frase — é a auditoria
 * do merge multi-fonte, e hoje ela não aparece em lugar nenhum da web.
 */
export function provenienciaResumo(p: Proposta): string | null {
  const prov = p.proveniencia;
  if (!prov || Object.keys(prov).length === 0) return null;
  const porScrape = Object.entries(prov)
    .filter(([, v]) => v === "scrape")
    .map(([k]) => k.replace(/_/g, " "));
  if (porScrape.length === 0) return "todos os campos por API";
  if (porScrape.length === Object.keys(prov).length) return "todos os campos por scraping";
  return `${porScrape.join(" e ")} por scraping`;
}

/** Percentual da contrapartida sobre o valor total, quando ambos existirem. */
export function percentualContrapartida(p: Proposta): number | null {
  const total = Number(p.valor_total);
  const cp = Number(p.contrapartida);
  if (!Number.isFinite(total) || !Number.isFinite(cp) || total <= 0) return null;
  return (cp / total) * 100;
}

export function municipioLabel(p: Proposta): string {
  const nome = p.municipio_nome ?? p.municipio_ibge;
  if (!nome) return "—";
  return p.uf ? `${nome}/${p.uf}` : nome;
}

export interface ResumoCaptacao {
  total: number;
  valorTotal: number;
  contrapartidaTotal: number;
  comPendencia: number;
  pendenciasTotal: number;
  comEmenda: number;
  prazoMaisProximo: { data: string; dias: number; proposta: Proposta } | null;
  porFonte: { fonte: string; total: number }[];
}

/** Agrega a lista para os KPIs do topo — tudo derivado do payload já carregado. */
export function resumirCaptacao(lista: Proposta[]): ResumoCaptacao {
  const porFonte = new Map<string, number>();
  let valorTotal = 0;
  let contrapartidaTotal = 0;
  let comPendencia = 0;
  let pendenciasTotal = 0;
  let comEmenda = 0;
  let prox: ResumoCaptacao["prazoMaisProximo"] = null;

  for (const p of lista) {
    porFonte.set(p.fonte, (porFonte.get(p.fonte) ?? 0) + 1);
    const v = Number(p.valor_total);
    if (Number.isFinite(v)) valorTotal += v;
    const c = Number(p.contrapartida);
    if (Number.isFinite(c)) contrapartidaTotal += c;

    const pend = pendencias(p);
    if (pend.length > 0) {
      comPendencia += 1;
      pendenciasTotal += pend.length;
    }
    if (p.emenda?.trim()) comEmenda += 1;

    const pr = prazoMaisProximo(p);
    const dias = pr ? diasAte(pr.data) : null;
    if (pr && dias !== null && (prox === null || dias < prox.dias)) {
      prox = { data: pr.data, dias, proposta: p };
    }
  }

  return {
    total: lista.length,
    valorTotal,
    contrapartidaTotal,
    comPendencia,
    pendenciasTotal,
    comEmenda,
    prazoMaisProximo: prox,
    porFonte: [...porFonte.entries()]
      .map(([fonte, total]) => ({ fonte, total }))
      .sort((a, b) => b.total - a.total),
  };
}
