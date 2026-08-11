"""Natureza jurídica do proponente/beneficiário — lente de consulta da captação.

Decisão de produto: duas lentes, não a taxonomia inteira da Receita Federal.

- ``entes_municipais`` — prefeitura, secretaria municipal, câmara de vereadores,
  fundo/autarquia/fundação municipal, consórcio intermunicipal.
- ``outros`` — todo o resto: organizações da sociedade civil, associações,
  entes estaduais/federais, empresas, cooperativas.

A classificação usa, nesta ordem: (1) o código da tabela de Natureza Jurídica
(CONCLA/Receita), quando a fonte informa; (2) marcadores textuais no nome/na
natureza do proponente; (3) um padrão por fonte (programas cujo beneficiário é,
por desenho, sempre o ente municipal). Sem nenhum sinal, cai em ``outros`` — só
marcamos ente municipal quando há evidência.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

ENTES_MUNICIPAIS = "entes_municipais"
OUTROS = "outros"

NATUREZAS: tuple[str, ...] = (ENTES_MUNICIPAIS, OUTROS)

ROTULOS: dict[str, str] = {
    ENTES_MUNICIPAIS: "Entes municipais",
    OUTROS: "Outros",
}

# Códigos da tabela de Natureza Jurídica (CONCLA/RFB) de esfera municipal.
# 103-1 Órgão Público do Poder Executivo Municipal · 106-6 Legislativo Municipal
# 112-0 Autarquia Municipal · 115-5 Fundação Pública de Direito Público Municipal
# 118-0 Órgão Público Autônomo Municipal · 124-4 Município
# 127-9 Fundação Pública de Direito Privado Municipal
# 130-9 / 133-3 Fundo Público (Indireta / Direta) Municipal
CODIGOS_MUNICIPAIS: frozenset[str] = frozenset(
    {"1031", "1066", "1120", "1155", "1180", "1244", "1279", "1309", "1333"}
)

# Marcadores textuais. "municipal" já cobre "intermunicipal" por substring.
_MARCADORES_MUNICIPAIS: tuple[str, ...] = (
    "prefeitura",
    "municipio",
    "municipal",
    "vereador",
)

# Valores curtos e exatos usados por algumas fontes no campo de esfera/tipo.
_EXATOS_MUNICIPAIS: frozenset[str] = frozenset({"m", "mun", "municipios"})

# Fontes cujo beneficiário é, por desenho do programa, o próprio ente municipal
# (repasse fundo a fundo ao município). Ponto de calibração ao ligar cada fonte.
PADRAO_POR_FONTE: dict[str, str] = {
    "transferegov_ff": ENTES_MUNICIPAIS,
    "fns": ENTES_MUNICIPAIS,
}


def _normalizar(valor: Any) -> str:
    """Minúsculas, sem acento e sem pontuação — para casar marcadores."""
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _codigo_municipal(codigo: Any) -> bool | None:
    """True/False se o código é reconhecido na tabela; None se não reconhecido."""
    digitos = re.sub(r"\D", "", str(codigo or ""))
    if len(digitos) != 4:
        return None
    return digitos in CODIGOS_MUNICIPAIS


def classificar(
    *valores: Any,
    codigo: Any = None,
    fonte: str | None = None,
    padrao: str | None = None,
) -> str:
    """Classifica em `entes_municipais` | `outros`.

    `valores` são textos candidatos (natureza jurídica, nome do proponente,
    esfera…), `codigo` é o código CONCLA/RFB quando a fonte informa, e `padrao`
    (ou o padrão da `fonte`) é o fallback quando não há sinal algum.
    """
    por_codigo = _codigo_municipal(codigo)
    if por_codigo is not None:
        return ENTES_MUNICIPAIS if por_codigo else OUTROS

    houve_texto = False
    for valor in valores:
        texto = _normalizar(valor)
        if not texto:
            continue
        houve_texto = True
        if texto in _EXATOS_MUNICIPAIS:
            return ENTES_MUNICIPAIS
        if any(marcador in texto for marcador in _MARCADORES_MUNICIPAIS):
            return ENTES_MUNICIPAIS

    if houve_texto:
        # Havia descrição e nada apontou para o município → não é ente municipal.
        return OUTROS
    return padrao or PADRAO_POR_FONTE.get(fonte or "", OUTROS)


def descrever(*valores: Any) -> str | None:
    """Primeiro texto não vazio — guardado como `natureza_juridica_descricao`."""
    for valor in valores:
        if valor not in (None, "", []):
            texto = str(valor).strip()
            if texto:
                return texto[:255]
    return None


def rotulo(natureza: str | None) -> str:
    return ROTULOS.get(natureza or OUTROS, ROTULOS[OUTROS])
