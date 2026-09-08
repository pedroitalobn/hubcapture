/**
 * Consultas salvas de propostas — as abas do construtor (§61).
 *
 * A aba é ENTIDADE, não estado de tela: vive no banco por usuário
 * (`/proposals/views`), então acompanha o gestor entre navegadores e máquinas.
 * Antes morava em `localStorage`, sob a chave `hub_captacao_abas` — o que
 * significava que a consulta que ele montou no escritório não existia no
 * notebook de casa.
 *
 * Este módulo é o DE-PARA entre as chaves da tela (camelCase) e as do
 * contrato (as MESMAS dos query params de `GET /proposals`). Ele mora num
 * lugar só: espalhado pela página, um filtro novo entra na tela e some ao
 * salvar, sem ninguém perceber.
 */

/** O recorte de uma aba, na linguagem da TELA. */
export interface FiltrosAba {
  /** Recorte de território DA ABA — vazio = todo o território do perfil. */
  municipios: string[];
  /** Origem do recurso DA ABA (grupo: transferegov, fns…) — vazio = todas. */
  fontes: string[];
  uf: string;
  ano: string;
  mes: string;
  tipo: "" | "cadastrada" | "disponivel";
  area: string;
  categoria: string;
  situacao: string;
  q: string;
  modalidade: string;
  orgao: string;
  naturezaJuridica: string;
  naturezaGrupo: string;
  qualificacao: string;
  ordenar: string;
  valorMin: string;
  valorMax: string;
  soFavoritas: boolean;
  pastaId: string;
}

export interface Aba {
  id: string;
  nome: string;
  filtros: FiltrosAba;
}

export const FILTROS_VAZIOS: FiltrosAba = {
  municipios: [],
  fontes: [],
  uf: "",
  ano: "",
  mes: "",
  tipo: "",
  area: "",
  categoria: "",
  situacao: "",
  q: "",
  modalidade: "",
  orgao: "",
  naturezaJuridica: "",
  naturezaGrupo: "",
  qualificacao: "",
  ordenar: "recentes",
  valorMin: "",
  valorMax: "",
  soFavoritas: false,
  pastaId: "",
};

/** O que o contrato guarda (schemas/consultas.py::FiltrosConsulta). */
type FiltrosApi = Record<string, unknown>;

const so = (v: string) => (v.trim() ? v.trim() : null);

/** Tela → contrato. Vazio vira `null`/`[]`: filtro ausente é filtro nenhum. */
export function paraApi(f: FiltrosAba): FiltrosApi {
  return {
    municipio: f.municipios,
    fonte: f.fontes,
    ano: f.ano ? [f.ano] : [],
    uf: so(f.uf),
    area: so(f.area),
    situacao: so(f.situacao),
    modalidade: so(f.modalidade),
    orgao: so(f.orgao),
    natureza_juridica: so(f.naturezaJuridica),
    natureza_grupo: so(f.naturezaGrupo),
    qualificacao: so(f.qualificacao),
    categoria: so(f.categoria),
    mes: so(f.mes),
    q: so(f.q),
    valor_min: so(f.valorMin),
    valor_max: so(f.valorMax),
    tipo: so(f.tipo),
    ordenar: so(f.ordenar),
    so_favoritas: f.soFavoritas,
    pasta_id: so(f.pastaId),
  };
}

const texto = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
const lista = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);

/** Contrato → tela. Chave que a API ainda não conhece não derruba a aba: cada
 *  campo cai no padrão, e o resto do recorte continua valendo. */
export function daApi(bruto: unknown): FiltrosAba {
  const f = (bruto ?? {}) as FiltrosApi;
  return {
    ...FILTROS_VAZIOS,
    municipios: lista(f.municipio),
    fontes: lista(f.fonte),
    ano: lista(f.ano)[0] ?? "",
    uf: texto(f.uf),
    area: texto(f.area),
    situacao: texto(f.situacao),
    modalidade: texto(f.modalidade),
    orgao: texto(f.orgao),
    naturezaJuridica: texto(f.natureza_juridica),
    naturezaGrupo: texto(f.natureza_grupo),
    qualificacao: texto(f.qualificacao),
    categoria: texto(f.categoria),
    mes: texto(f.mes),
    q: texto(f.q),
    valorMin: texto(f.valor_min),
    valorMax: texto(f.valor_max),
    tipo: (texto(f.tipo) || "") as FiltrosAba["tipo"],
    ordenar: texto(f.ordenar) || FILTROS_VAZIOS.ordenar,
    soFavoritas: Boolean(f.so_favoritas),
    pastaId: texto(f.pasta_id),
  };
}

/** Uma aba como a API a devolve. */
export function abaDaApi(bruto: {
  id: string;
  nome: string;
  filtros?: unknown;
}): Aba {
  return { id: bruto.id, nome: bruto.nome, filtros: daApi(bruto.filtros) };
}

// ── Migração das abas que ficaram no navegador ──────────────────────────────
// A chave antiga some assim que as abas locais viram registros; enquanto isso
// não acontece (API fora do ar, por exemplo), ela fica onde está — perder a
// consulta do gestor por causa de uma falha de rede seria pior que repetir a
// migração na próxima carga.
export const CHAVE_ABAS_LOCAIS = "hub_captacao_abas";

export function abasLocais(): { nome: string; filtros: FiltrosAba }[] {
  if (typeof window === "undefined") return [];
  try {
    const bruto = window.localStorage.getItem(CHAVE_ABAS_LOCAIS);
    if (!bruto) return [];
    const lista = JSON.parse(bruto) as { nome?: string; filtros?: unknown }[];
    if (!Array.isArray(lista)) return [];
    return lista
      .filter((a) => a && typeof a === "object")
      .map((a, i) => ({
        nome: (a.nome ?? `Frente ${i + 1}`).slice(0, 120),
        // as abas locais guardavam as chaves da TELA (camelCase), não as do
        // contrato — por isso a leitura aqui não passa por `daApi`
        filtros: { ...FILTROS_VAZIOS, ...((a.filtros ?? {}) as Partial<FiltrosAba>) },
      }));
  } catch {
    return []; // estado corrompido → o gestor recomeça, sem tela quebrada
  }
}

export function esquecerAbasLocais(): void {
  try {
    window.localStorage.removeItem(CHAVE_ABAS_LOCAIS);
  } catch {
    /* storage bloqueado: a migração só não some da próxima vez */
  }
}

/** Recorte "de fábrica"? Serve para saber se a aba inicial criada pela API
 *  pode ser substituída pelas abas que vieram do navegador. */
export function abaVazia(a: Aba): boolean {
  return JSON.stringify(a.filtros) === JSON.stringify(FILTROS_VAZIOS);
}
