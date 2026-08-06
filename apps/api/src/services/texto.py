"""Normalização de APRESENTAÇÃO de texto das fontes de governo.

As bases gravam quase tudo em CAIXA ALTA ("MTUR/SECULT - ALDIR BLANC -
MUNICÍPIOS", "FUNDO_A_FUNDO", "DISPONIBILIZADO"). Jogado direto num documento
isso grita e é mais lento de ler. Aqui a normalização é só de exibição — o dado
gravado continua idêntico à origem (a conferência é pelo link da fonte oficial).

Espelho em Python do `apps/web/lib/format.ts::humanizarCaixa`: a mesma regra
serve a tela e o PDF, senão o espelho compartilhado sairia gritando enquanto o
painel não grita.
"""

from __future__ import annotations

import re

# Siglas que continuam em caixa alta. Com 3 letras ou menos a regra já mantém
# (UF, SUS, UBS, FNS…); aqui entram só as de 4+ letras.
SIGLAS = frozenset(
    (
        "MTUR SECULT FNDE FNS SERPRO SIMEC SISMOB SIORB SICONFI CAUC CAPAG CNPJ IBGE "
        "SAMU CRAS CREAS SUAS PNAE PNATE SIAFI SICONV SIGEF PAC OGU APF LOA LDO PPA "
        "FPM ICMS IPVA FUNDEB CAPS SUS MEC"
    ).split()
)

# Conectivos que ficam minúsculos quando não abrem o texto.
CONECTIVOS = frozenset(
    (
        "de da do das dos e em no na nos nas a o as os ao aos à às para por com sem "
        "sob sobre entre ou pelo pela pelos pelas num numa"
    ).split()
)

# Palavras curtas que NÃO são sigla — sem isto a regra "3 letras ou menos =
# sigla" deixaria "LEI" e "UMA" gritando no meio de uma frase normalizada.
CURTAS_COMUNS = frozenset(
    (
        "um uma uns que não nao sua seu até ate são sao ano rua dia mês mes sim tem "
        "ser ter foi faz vai mil via lei seq"
    ).split()
)

_LETRAS = re.compile(r"[^\W\d_]", re.UNICODE)
_TOKENS = re.compile(r"([^\w]+|_+)", re.UNICODE)


def _eh_caixa_alta(texto: str) -> bool:
    """É predominantemente CAIXA ALTA? (ignora dígitos e pontuação)"""
    letras = _LETRAS.findall(texto)
    if len(letras) < 2:
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    return maiusculas / len(letras) >= 0.8


def _palavra(token: str, primeira: bool) -> str:
    if any(c.isdigit() for c in token):
        return token  # códigos e datas ficam como vieram
    nu = "".join(_LETRAS.findall(token))
    if not nu:
        return token
    minusculo = token.lower()
    capitalizada = minusculo[:1].upper() + minusculo[1:]
    if minusculo in CONECTIVOS:
        return capitalizada if primeira else minusculo
    if nu.upper() in SIGLAS:
        return token.upper()
    if len(nu) <= 3 and minusculo not in CURTAS_COMUNS:
        return token.upper()
    return capitalizada


def humanizar_caixa(texto: object) -> str:
    """ "MTUR/SECULT - ALDIR BLANC" → "MTUR/SECULT - Aldir Blanc".

    "FUNDO_A_FUNDO" → "Fundo a Fundo". Texto já em caixa mista passa intacto.
    """
    if texto is None:
        return ""
    original = str(texto)
    bruto = original.replace("_", " ").strip()
    if not bruto or not _eh_caixa_alta(bruto):
        return original
    primeira = True
    saida: list[str] = []
    for parte in _TOKENS.split(bruto):
        if not parte:
            continue
        if _TOKENS.fullmatch(parte):
            saida.append(" " if "_" in parte else parte)  # delimitador
            continue
        saida.append(_palavra(parte, primeira))
        primeira = False
    return "".join(saida)
