"""Busca de NOME tolerante — acento, caixa e erro de digitação.

O gestor digita nome de município de ouvido: "apuiarez" é Apuiarés, "mosoro"
é Mossoró, "chique chique" é Xique-Xique. A busca antiga casava só prefixo e
trecho sem acento, então uma letra trocada devolvia "nenhum município" com o
município certo a uma tecla de distância.

Três camadas, da mais certa para a mais solta:

1. EXATA      — sem acento/caixa: trecho do nome ou começo de palavra;
2. FONÉTICA   — as trocas do português falado (z/s, ç/ss, ch/x, y/i, qu/k,
                h mudo, letra dobrada…);
3. APROXIMADA — distância de edição por palavra, com tolerância pelo tamanho
                do que foi digitado.

A aproximada só entra quando as duas primeiras não acham nada — digitar "sao"
mostra os "São …", não um "Salto" de brinde.

Espelho em TypeScript: `apps/web/lib/busca.ts` (os menus do painel usam a
mesma regra). Mudou aqui, muda lá.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")

_NAO_ALFANUM = re.compile(r"[^a-z0-9]+")

# Ordem importa: dígrafos antes das letras soltas, letra dobrada por último.
_REGRAS_FONETICAS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(padrao), troca)
    for padrao, troca in (
        (r"ph", "f"),
        (r"[cs]h", "x"),
        (r"qu(?=[ei])", "k"),
        (r"gu(?=[ei])", "g"),
        (r"g(?=[ei])", "j"),
        (r"c(?=[ei])", "s"),
        (r"[cq]", "k"),
        (r"z", "s"),
        (r"y", "i"),
        (r"w", "v"),
        (r"h", ""),
        (r"m(?=[^aeiou]|$)", "n"),
        (r"(.)\1+", r"\1"),
    )
)


def normalizar(texto: str) -> str:
    """Sem acento, minúsculo, pontuação vira espaço."""
    sem_acento = unicodedata.normalize("NFD", texto or "")
    base = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn").lower()
    return _NAO_ALFANUM.sub(" ", base).strip()


def palavras(texto: str) -> list[str]:
    n = normalizar(texto)
    return n.split(" ") if n else []


def fonetica(palavra: str) -> str:
    """Forma fonética aproximada de UMA palavra já normalizada."""
    for padrao, troca in _REGRAS_FONETICAS:
        palavra = padrao.sub(troca, palavra)
    return palavra


def distancia(a: str, b: str, teto: int | None = None) -> int:
    """Damerau-Levenshtein (alinhamento ótimo): troca, falta, sobra e duas
    letras invertidas custam 1. Com `teto`, para cedo devolvendo `teto + 1`."""
    if a == b:
        return 0
    if teto is not None and abs(len(a) - len(b)) > teto:
        return teto + 1
    antes = [0] * (len(b) + 1)
    linha = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        atual = [i] + [0] * len(b)
        menor = i
        for j in range(1, len(b) + 1):
            custo = 0 if a[i - 1] == b[j - 1] else 1
            v = min(linha[j] + 1, atual[j - 1] + 1, linha[j - 1] + custo)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, antes[j - 2] + 1)
            atual[j] = v
            menor = min(menor, v)
        if teto is not None and menor > teto:
            return teto + 1
        antes, linha = linha, atual
    return linha[-1]


def tolerancia(tamanho: int) -> int:
    """Erros tolerados numa palavra digitada: até 3 letras, nenhum (com tão
    pouco, um erro casa com meia lista — "xyz" viraria Xique-Xique); até 5,
    um; daí em diante, dois."""
    if tamanho <= 3:
        return 0
    if tamanho <= 5:
        return 1
    return 2


def _distancia_prefixo(digitado: str, palavra: str, teto: int) -> int:
    """Menor distância entre o digitado e o COMEÇO da palavra — "apuiar" ainda
    está digitando "Apuiarés", não errou."""
    melhor = distancia(digitado, palavra, teto)
    for corte in range(len(digitado) - 1, len(digitado) + 2):
        if 0 < corte < len(palavra):
            melhor = min(melhor, distancia(digitado, palavra[:corte], teto))
    return melhor


@dataclass(frozen=True, slots=True)
class Termos:
    """Texto pronto para comparar: palavras normalizadas e a forma fonética
    de cada uma. Pré-calcular vale a pena quando o alvo é uma lista grande e
    fixa (os ~5,5 mil municípios do IBGE)."""

    palavras: tuple[str, ...]
    fon: tuple[str, ...]


def preparar(texto: str) -> Termos:
    ps = tuple(palavras(texto))
    return Termos(ps, tuple(fonetica(p) for p in ps))


def pontuar_preparado(consulta: Termos, alvo: Termos) -> int | None:
    """Camada em que a consulta casa com o alvo (0 exata · 1 fonética · 2+
    aproximada, quanto maior pior) — ou None quando não casa."""
    if not consulta.palavras:
        return 0
    if not alvo.palavras:
        return None

    # 1. exata: o trecho inteiro, ou cada palavra começando uma do alvo
    if " ".join(consulta.palavras) in " ".join(alvo.palavras):
        return 0
    if all(any(p.startswith(q) for p in alvo.palavras) for q in consulta.palavras):
        return 0

    # 2. fonética: a mesma comparação sobre a forma falada
    junto = "".join(consulta.fon)
    if len(junto) >= 3 and junto in "".join(alvo.fon):
        return 1
    if all(q and any(p.startswith(q) for p in alvo.fon) for q in consulta.fon):
        return 1

    # 3. aproximada: cada palavra digitada a poucos erros de uma do alvo. A
    #    primeira letra (escrita ou falada) tem de bater — quase nunca é ela
    #    o erro, e é o corte que deixa a varredura dos 5,5 mil municípios
    #    barata.
    total = 0
    for q, qf in zip(consulta.palavras, consulta.fon, strict=True):
        teto = tolerancia(len(q))
        melhor = teto + 1
        for p, pf in zip(alvo.palavras, alvo.fon, strict=True):
            if p[:1] != q[:1] and pf[:1] != qf[:1]:
                continue
            melhor = min(
                melhor,
                _distancia_prefixo(q, p, teto),
                _distancia_prefixo(qf, pf, teto),
            )
            if melhor == 0:
                break
        if melhor > teto:
            return None
        total += melhor
    return 2 + total


def pontuar(termo: str, texto: str) -> int | None:
    return pontuar_preparado(preparar(termo), preparar(texto))


def filtrar(
    itens: Iterable[T],
    termo: str,
    termos: Callable[[T], Termos],
) -> list[T]:
    """Filtra pelo termo. As camadas exata e fonética preservam a ORDEM
    original; a aproximada só aparece quando as outras não acharam nada, da
    mais parecida para a menos. `termos` devolve o alvo já preparado
    (`preparar(...)`) — quem tem lista fixa calcula uma vez e guarda."""
    lista = list(itens)
    consulta = preparar(termo)
    if not consulta.palavras:
        return lista
    certas: list[T] = []
    aproximadas: list[tuple[int, int, T]] = []
    for pos, item in enumerate(lista):
        nota = pontuar_preparado(consulta, termos(item))
        if nota is None:
            continue
        if nota <= 1:
            certas.append(item)
        else:
            aproximadas.append((nota, pos, item))
    if certas:
        return certas
    aproximadas.sort(key=lambda a: (a[0], a[1]))
    return [item for _, _, item in aproximadas]
