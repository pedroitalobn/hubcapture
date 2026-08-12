/* ─────────────────────────────────────────── Caixa alta das fontes ────────
   As bases do governo gravam quase tudo em CAIXA ALTA ("MTUR/SECULT - ALDIR
   BLANC - MUNICÍPIOS", "DISPONIBILIZADO", "FUNDO_A_FUNDO"). Jogado direto na
   tela, isso grita, quebra o ritmo tipográfico e é mais lento de ler. Aqui a
   normalização é de APRESENTAÇÃO: o dado gravado continua idêntico à origem —
   quem quiser conferir tem o link "Fonte oficial ↗". */

// Siglas que continuam em caixa alta (com 3 letras ou menos, a regra já mantém:
// UF, SUS, UBS, FNS…). Só entram aqui as de 4+ letras.
const SIGLAS = new Set([
  "MTUR", "SECULT", "FNDE", "FNS", "SERPRO", "SIMEC", "SISMOB", "SIORB", "SICONFI",
  "CAUC", "CAPAG", "CNPJ", "IBGE", "SAMU", "CRAS", "CREAS", "SUAS", "PNAE", "PNATE",
  "SIAFI", "SICONV", "SIGEF", "CEP", "PAC", "OGU", "APF", "LOA", "LDO", "PPA", "FPM",
  "ICMS", "IPVA", "FUNDEB", "PNATE", "CAPS", "SUS",
]);

// Conectivos que ficam minúsculos quando não abrem o texto.
const CONECTIVOS = new Set([
  "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "a", "o",
  "as", "os", "ao", "aos", "à", "às", "para", "por", "com", "sem", "sob", "sobre",
  "entre", "ou", "pelo", "pela", "pelos", "pelas", "num", "numa", "d'água",
]);

// Palavras curtas que NÃO são sigla — sem isto a regra "3 letras ou menos = sigla"
// deixaria "(UMA)" e "LEI" gritando no meio de uma frase normalizada.
const CURTAS_COMUNS = new Set([
  "um", "uma", "uns", "que", "não", "nao", "sua", "seu", "até", "ate", "são",
  "sao", "ano", "rua", "dia", "mês", "mes", "sim", "tem", "ser", "ter", "foi",
  "faz", "vai", "mil", "via", "lei", "seq", "nº", "n°", "seis", "seu",
]);

/** É predominantemente CAIXA ALTA? (ignora dígitos e pontuação) */
function ehCaixaAlta(texto: string): boolean {
  const letras = texto.replace(/[^\p{L}]/gu, "");
  if (letras.length < 2) return false;
  const maiusculas = letras.replace(/[^\p{Lu}]/gu, "").length;
  return maiusculas / letras.length >= 0.8;
}

function palavra(token: string, primeira: boolean): string {
  if (/\d/.test(token)) return token; // códigos e datas ficam como vieram
  const nu = token.replace(/[^\p{L}]/gu, "");
  if (!nu) return token;
  const minusculo = token.toLowerCase();
  const capitalizada = minusculo.charAt(0).toUpperCase() + minusculo.slice(1);
  // conectivo antes de sigla: "EM ANÁLISE" abre a frase com "Em", não com "EM"
  if (CONECTIVOS.has(minusculo)) return primeira ? capitalizada : minusculo;
  if (SIGLAS.has(nu.toUpperCase())) return token.toUpperCase();
  if (nu.length <= 3 && !CURTAS_COMUNS.has(minusculo)) return token.toUpperCase();
  return capitalizada;
}

/**
 * "MTUR/SECULT - ALDIR BLANC - MUNICÍPIOS" → "MTUR/SECULT - Aldir Blanc -
 * Municípios"; "FUNDO_A_FUNDO" → "Fundo a Fundo"; "DISPONIBILIZADO" →
 * "Disponibilizado". Texto que já vem em caixa mista passa intacto.
 */
export function humanizarCaixa(texto?: string | null): string {
  if (texto === null || texto === undefined) return "";
  const bruto = String(texto).replace(/_/g, " ").trim();
  if (!bruto || !ehCaixaAlta(bruto)) return String(texto);
  let primeira = true;
  // separa mantendo os delimitadores (espaço, / , - , ( ) etc.)
  return bruto
    .split(/([^\p{L}\p{N}]+)/u)
    .map((parte) => {
      if (!/[\p{L}\p{N}]/u.test(parte)) return parte; // delimitador
      const saida = palavra(parte, primeira);
      primeira = false;
      return saida;
    })
    .join("");
}

/* ──────────────────────────────────────────── Recorte de texto longo ─────
   As fontes não separam "título" de "descrição": o `objeto` que vira título da
   proposta chega com o projeto inteiro dentro (o de um edital de cultura passa
   de 2 mil caracteres). Sem teto, o título come a tela e empurra valor, empenho
   e prazo — os dados que decidem a ação — para baixo da dobra. */

/**
 * Recorta em `limite` caracteres, sempre numa palavra inteira. Devolve também
 * se houve corte, para quem chama decidir se oferece o texto completo (é o que
 * `TextoLimitado` faz, com o modal de "ver completo").
 */
export function recortarTexto(
  texto: string | null | undefined,
  limite: number,
): { trecho: string; cortado: boolean } {
  const t = String(texto ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (t.length <= limite) return { trecho: t, cortado: false };
  const bruto = t.slice(0, limite);
  const espaco = bruto.lastIndexOf(" ");
  // recua até a última palavra inteira — mas não a ponto de jogar fora o
  // recorte (uma "palavra" de 200 caracteres, comum em URL colada na descrição)
  const corte = espaco > limite * 0.6 ? espaco : bruto.length;
  const trecho = t.slice(0, corte).replace(/[\s.,;:!?/\-–—]+$/u, "");
  return { trecho: `${trecho}…`, cortado: true };
}

/**
 * Território de um registro. Regra de exibição (seção 23 do CLAUDE.md): o NOME
 * do município lidera; o código IBGE é dado secundário. Nenhuma tela deve usar
 * o código sozinho como identidade do registro — para isso existem estes dois
 * helpers, e não um `municipio_nome ?? municipio_ibge` espalhado.
 */
export interface MunicipioRef {
  municipio_nome?: string | null;
  municipio_ibge?: string | null;
  uf?: string | null;
}

/** Linha principal: "São Paulo/SP" — nunca um número solto. */
export function municipioPrincipal(m: MunicipioRef): string {
  const nome = humanizarCaixa(m.municipio_nome).trim();
  if (nome) return m.uf ? `${nome}/${m.uf}` : nome;
  // sem nome (a fonte não trouxe e o perfil não tem): rotula o código
  if (m.municipio_ibge) return `Município ${m.municipio_ibge}`;
  return "Município não informado";
}

/** Linha de apoio: o código IBGE (ou a UF, quando o código já apareceu). */
export function municipioSecundario(m: MunicipioRef): string | null {
  if (humanizarCaixa(m.municipio_nome).trim()) {
    return m.municipio_ibge ? `IBGE ${m.municipio_ibge}` : null;
  }
  return m.uf ? `UF ${m.uf}` : null;
}

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

export type TomPrazo = "ok" | "warn" | "danger";

/**
 * Urgência de um prazo → tom semântico. Uma regra só para todo o app: a lista
 * de captação pintava vencido de `text-ink-3` (cinza, REBAIXADO) enquanto
 * "≤30 dias" saía em âmbar — o dado mais urgente era o menos visível.
 * Aceita a data ou os dias já computados pela API (`dias_restantes`).
 */
export function tomPrazo(
  entrada?: string | number | null,
  hoje = new Date(),
): TomPrazo | undefined {
  const d =
    typeof entrada === "number" ? entrada : diasAte(entrada ?? null, hoje);
  if (d === null || d === undefined) return undefined;
  if (d <= 7) return "danger"; // vencido ou vencendo nesta semana
  if (d <= 30) return "warn";
  return "ok";
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
