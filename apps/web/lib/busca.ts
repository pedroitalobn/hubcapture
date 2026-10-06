/**
 * Busca TOLERANTE dos menus do painel — acento, caixa e erro de digitação.
 *
 * O gestor digita nome de município de ouvido: "apuiarez" é Apuiarés,
 * "mosoro" é Mossoró, "chique chique" é Xique-Xique. O filtro antigo era um
 * `includes` cru sobre o rótulo, então qualquer letra trocada esvaziava a
 * lista e a tela dizia "nada com esse nome" com o município bem ali.
 *
 * Três camadas, da mais certa para a mais solta:
 *   1. EXATA      — sem acento/caixa: trecho do rótulo ou começo de palavra;
 *   2. FONÉTICA   — as trocas do português falado (z/s, ç/ss, ch/x, y/i,
 *                   qu/k, h mudo, letra dobrada…);
 *   3. APROXIMADA — distância de edição por palavra, com tolerância pelo
 *                   tamanho do que foi digitado.
 * A aproximada só entra quando as duas primeiras não acham nada: digitar "sao"
 * mostra os "São …" e não um "Salto" de brinde.
 *
 * Espelho em Python: `apps/api/src/services/busca_nome.py` (a busca de
 * municípios do onboarding usa a mesma regra).
 */

/** Sem acento, minúsculo, pontuação vira espaço. */
export function normalizarBusca(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function palavras(texto: string): string[] {
  const n = normalizarBusca(texto);
  return n ? n.split(" ") : [];
}

/** Forma fonética aproximada de UMA palavra já normalizada. A ordem importa:
 *  dígrafos antes das letras soltas, letra dobrada por último. */
export function fonetica(palavra: string): string {
  return palavra
    .replace(/ph/g, "f")
    .replace(/[cs]h/g, "x")
    .replace(/qu(?=[ei])/g, "k")
    .replace(/gu(?=[ei])/g, "g")
    .replace(/g(?=[ei])/g, "j")
    .replace(/c(?=[ei])/g, "s")
    .replace(/[cq]/g, "k")
    .replace(/z/g, "s")
    .replace(/y/g, "i")
    .replace(/w/g, "v")
    .replace(/h/g, "")
    .replace(/m(?=[^aeiou]|$)/g, "n")
    .replace(/(.)\1+/g, "$1");
}

/** Damerau-Levenshtein (alinhamento ótimo): troca, falta, sobra e duas
 *  letras invertidas custam 1 cada. Para cedo quando passa de `teto`. */
export function distancia(a: string, b: string, teto = Infinity): number {
  if (a === b) return 0;
  if (Math.abs(a.length - b.length) > teto) return teto + 1;
  const m = a.length;
  const n = b.length;
  let antes: number[] = new Array(n + 1).fill(0);
  let linha: number[] = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const atual: number[] = [i];
    let menor = i;
    for (let j = 1; j <= n; j++) {
      const custo = a[i - 1] === b[j - 1] ? 0 : 1;
      let v = Math.min(linha[j]! + 1, atual[j - 1]! + 1, linha[j - 1]! + custo);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        v = Math.min(v, antes[j - 2]! + 1);
      }
      atual[j] = v;
      if (v < menor) menor = v;
    }
    if (menor > teto) return teto + 1;
    antes = linha;
    linha = atual;
  }
  return linha[n]!;
}

/** Quantos erros se tolera numa palavra digitada: até 3 letras, nenhum (com
 *  tão pouco, um erro casa com meia lista — "xyz" viraria Xique-Xique); até
 *  5, um; daí em diante, dois. */
function tolerancia(tamanho: number): number {
  if (tamanho <= 3) return 0;
  if (tamanho <= 5) return 1;
  return 2;
}

/** Menor distância entre o que foi digitado e o COMEÇO de uma palavra do
 *  rótulo — "apuiar" ainda está digitando "Apuiarés", não errou. */
function distanciaPrefixo(digitado: string, palavra: string, teto: number): number {
  let melhor = distancia(digitado, palavra, teto);
  for (let corte = digitado.length - 1; corte <= digitado.length + 1; corte++) {
    if (corte <= 0 || corte >= palavra.length) continue;
    melhor = Math.min(melhor, distancia(digitado, palavra.slice(0, corte), teto));
  }
  return melhor;
}

/** Camada em que o termo casa com o texto (0 exata · 1 fonética ·
 *  2+ aproximada, quanto maior pior) — ou `null` quando não casa. */
export function pontuar(termo: string, texto: string): number | null {
  const consulta = palavras(termo);
  if (consulta.length === 0) return 0;
  const alvo = palavras(texto);
  if (alvo.length === 0) return null;

  // 1. exata: o trecho inteiro no rótulo, ou cada palavra começando uma dele
  if (alvo.join(" ").includes(consulta.join(" "))) return 0;
  if (consulta.every((q) => alvo.some((p) => p.startsWith(q)))) return 0;

  // 2. fonética: a mesma comparação sobre a forma falada
  const alvoFon = alvo.map(fonetica);
  const consultaFon = consulta.map(fonetica);
  if (alvoFon.join("").includes(consultaFon.join("")) && consultaFon.join("").length >= 3) {
    return 1;
  }
  if (consultaFon.every((q) => q && alvoFon.some((p) => p.startsWith(q)))) return 1;

  // 3. aproximada: cada palavra digitada a poucos erros de uma do rótulo. A
  //    primeira letra (escrita ou falada) tem de bater — quase nunca é ela o
  //    erro, e é o corte que mantém o espelho em Python barato sobre os 5,5
  //    mil municípios do IBGE.
  let total = 0;
  for (let i = 0; i < consulta.length; i++) {
    const q = consulta[i]!;
    const qf = consultaFon[i]!;
    const teto = tolerancia(q.length);
    let melhor = teto + 1;
    for (let j = 0; j < alvo.length; j++) {
      if (alvo[j]![0] !== q[0] && alvoFon[j]![0] !== qf[0]) continue;
      melhor = Math.min(
        melhor,
        distanciaPrefixo(q, alvo[j]!, teto),
        distanciaPrefixo(qf, alvoFon[j]!, teto),
      );
      if (melhor === 0) break;
    }
    if (melhor > teto) return null;
    total += melhor;
  }
  return 2 + total;
}

/**
 * Filtra (e ordena) uma lista pelo que foi digitado. Sem termo, devolve a
 * lista intacta. As camadas exata e fonética preservam a ORDEM original (as
 * listas já vêm ordenadas com sentido — faceta por contagem, ano por data);
 * a aproximada só aparece quando as outras não acharam nada, da mais parecida
 * para a menos.
 */
export function filtrarPorBusca<T>(
  lista: readonly T[],
  termo: string,
  texto: (item: T) => string,
): T[] {
  if (!normalizarBusca(termo)) return [...lista];
  const certas: T[] = [];
  const aproximadas: { item: T; nota: number; pos: number }[] = [];
  lista.forEach((item, pos) => {
    const nota = pontuar(termo, texto(item));
    if (nota === null) return;
    if (nota <= 1) certas.push(item);
    else aproximadas.push({ item, nota, pos });
  });
  if (certas.length > 0) return certas;
  return aproximadas
    .sort((a, b) => a.nota - b.nota || a.pos - b.pos)
    .map((a) => a.item);
}
