"""Categorias da proposta — as "pílulas" do painel.

Duas camadas sobre a MESMA taxonomia fechada:

1. **Determinística** (`classificar`): palavra-chave sobre título/objeto/órgão/
   programa. Roda sempre, sem rede e sem custo — o painel nunca fica sem pílula,
   nem quando não há credencial de LLM configurada.
2. **IA** (`ai/resumo.gerar_curadoria`): refina a escolha e escreve o resumo. Só
   entra quando há chave no painel admin; sem ela, a camada 1 já entregou.

A taxonomia é fechada de propósito: a pílula também é FILTRO
(`/proposals?categoria=saude`), então o vocabulário precisa ser estável. Fonte
nova não inventa categoria — mapeia nas existentes, ou acrescenta-se um item
aqui (um lugar só; filtro, faceta, CSV e pílula acompanham sozinhos).

**Casamento por palavra, nunca por substring.** Cada termo vira `\\bTERMO\\b`;
com `*` no fim, `\\bTERMO` (aceita sufixo). Sem isso "cultura" acha Cultura
dentro de "agriCULTURA" e "sus" dentro de "SUStentável" — os dois erros que a
primeira versão cometia num corpus real do TransfereGov.
"""

from __future__ import annotations

import re
import unicodedata

# fmt: off
# (slug, rótulo, termos) — termos sem acento, minúsculos; `*` = aceita sufixo.
CATEGORIAS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("saude", "Saúde", (
        "saude*", "hospital*", "ubs", "upa", "samu", "posto de saude", "medicament*",
        "vacina*", "sus", "ambulanc*", "odontolog*", "enfermag*", "caps", "farmacia*",
        "vigilancia sanitaria", "atencao basica", "sismob",
    )),
    ("educacao", "Educação", (
        "educac*", "escola*", "creche*", "ensino", "fnde", "merenda", "professor*",
        "aluno*", "universidade*", "pnae", "pnate", "caminho da escola", "simec", "mec",
    )),
    ("infraestrutura", "Infraestrutura e obras", (
        "pavimenta*", "recapea*", "calcament*", "paralelepipedo*", "ponte*", "drenagem",
        "urbaniza*", "praca*", "meio-fio", "asfalt*", "estrada*", "terraplan*", "obra*",
        "construcao", "reforma*", "muro de contencao", "meio fio",
    )),
    ("saneamento", "Saneamento", (
        "saneament*", "esgoto*", "abastecimento de agua", "agua potavel", "residuos",
        "aterro sanitario", "coleta de lixo", "modulo sanitario", "poco artesiano",
        "cisterna*",
    )),
    ("mobilidade", "Mobilidade e transporte", (
        "transporte*", "mobilidade", "onibus", "veicul*", "frota", "rodoviari*",
        "ciclovia*", "sinalizacao viaria", "terminal de passageiros",
    )),
    ("cultura", "Cultura", (
        "cultura", "culturais", "cultural", "aldir blanc", "paulo gustavo", "museu*",
        "teatro*", "patrimonio historico", "biblioteca*", "artistic*", "festival*",
        "secult", "fundo nacional da cultura",
    )),
    ("esporte", "Esporte e lazer", (
        "esporte*", "esportiv*", "quadra*", "ginasio*", "campo de futebol", "lazer",
        "academia da saude", "academia ao ar livre", "piscina*", "arena",
    )),
    ("assistencia_social", "Assistência social", (
        "assistencia social", "cras", "creas", "sistema unico de assistencia social",
        "vulnerabilidade", "abrigo*", "idoso*", "crianca e adolescente",
        "seguranca alimentar", "inclusao social", "pessoa com deficiencia",
    )),
    ("agricultura", "Agricultura e desenvolvimento rural", (
        "agricultura", "agricola*", "produtor* rural*", "agricultura familiar", "trator*",
        "patrulha mecanizada", "feira*", "pesca", "irriga*", "aquicultura",
        "abastecimento alimentar", "produtores rurais",
    )),
    ("meio_ambiente", "Meio ambiente", (
        "meio ambiente", "ambiental*", "reflorest*", "sustentav*", "sustentabilidade",
        "climatic*",
        "nascente*", "parque natural", "arboriza*", "energia solar", "fotovoltaic*",
    )),
    ("seguranca", "Segurança pública", (
        "seguranca publica", "guarda municipal", "videomonitor*", "defesa civil",
        "bombeiro*", "iluminacao publica", "policia*",
    )),
    ("habitacao", "Habitação", (
        "habitac*", "moradia*", "casa popular", "regularizacao fundiaria",
        "unidade* habitacional*",
    )),
    ("turismo", "Turismo", ("turismo", "turistic*", "mtur", "ministerio do turismo")),
    ("tecnologia", "Tecnologia e inovação", (
        "tecnologia*", "inovacao", "digital*", "informatica", "conectividade",
        "internet", "software", "telecentro*",
    )),
    ("gestao", "Gestão pública", (
        "gestao", "capacita*", "modernizacao administrativa", "material permanente",
        "equipamento* permanente*", "mobiliario", "estruturacao da administracao",
    )),
)
# fmt: on

SLUGS: tuple[str, ...] = tuple(slug for slug, _, _ in CATEGORIAS)
ROTULOS: dict[str, str] = {slug: rotulo for slug, rotulo, _ in CATEGORIAS}

# no máximo 3 pílulas por proposta — mais que isso deixa de classificar e vira ruído
LIMITE_PADRAO = 3


def _compilar(termo: str) -> re.Pattern[str]:
    """`\\bTERMO\\b`; com `*` no fim, `\\bTERMO` (casa o sufixo flexionado)."""
    if termo.endswith("*"):
        return re.compile(rf"\b{re.escape(termo[:-1])}")
    return re.compile(rf"\b{re.escape(termo)}\b")


_PADROES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = tuple(
    (slug, tuple(_compilar(t) for t in termos)) for slug, _, termos in CATEGORIAS
)


def _normalizar(texto: str) -> str:
    """Minúsculas sem acento — a forma em que os padrões são casados."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    ).lower()


def classificar(*textos: str | None, limite: int = LIMITE_PADRAO) -> list[str]:
    """Categorias prováveis a partir dos textos da proposta (mais forte primeiro).

    Sem rede e sem custo: é o que garante pílula em toda proposta, com ou sem IA.
    Devolve [] quando nada casa — melhor nenhuma pílula do que uma errada.
    """
    corpus = _normalizar(" ".join(t for t in textos if t)).strip()
    if not corpus:
        return []
    pontuados: list[tuple[int, int, str]] = []
    for ordem, (slug, padroes) in enumerate(_PADROES):
        acertos = sum(1 for p in padroes if p.search(corpus))
        if acertos:
            # desempate pela ordem da taxonomia (estável entre execuções)
            pontuados.append((-acertos, ordem, slug))
    pontuados.sort()
    return [slug for _, _, slug in pontuados[:limite]]


def sanear(slugs: object, limite: int = LIMITE_PADRAO) -> list[str]:
    """Mantém só slugs conhecidos, sem repetição e no limite (entrada da IA)."""
    if not isinstance(slugs, (list, tuple)):
        return []
    vistos: list[str] = []
    for s in slugs:
        slug = str(s).strip().lower()
        if slug in ROTULOS and slug not in vistos:
            vistos.append(slug)
    return vistos[:limite]


def rotular(slugs: list[str] | None) -> list[dict[str, str]]:
    """[{'slug','rotulo'}] — o formato que a API entrega para as pílulas do painel."""
    return [{"slug": s, "rotulo": ROTULOS[s]} for s in (slugs or []) if s in ROTULOS]
