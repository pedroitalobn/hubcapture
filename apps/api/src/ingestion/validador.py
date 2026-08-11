"""Gate de qualidade da ingestão — só entra no cache o que é proposta.

O pipeline confiava no connector: tudo que ele devolvia virava linha em
`propostas`. Quando o scraping falha, porém, ele não levanta exceção — ele
devolve *alguma coisa*: a página de erro do portal, o desafio do Cloudflare, o
aviso de "habilite o JavaScript", ou um pacote vazio com o código da coleta no
lugar do identificador. Normalizado, isso virava uma proposta sem título, sem
valor e sem número no painel do gestor, indistinguível de uma proposta real —
com "scrape-<ibge>" onde deveria estar o nome do programa.

Este módulo é a porta: `triar` separa o que pode ser gravado do que precisa ser
descartado, e diz POR QUÊ. Determinístico e sem rede — por isso cabe dentro do
request, na frente de todo upsert (`services/consulta_avulsa`). A análise por
IA (`ai/validacao.py`) é a segunda camada, para o resíduo que passa por aqui
parecendo dado real.

Regra de calibração: na dúvida, ACEITA. Um falso positivo aqui esconde do
gestor uma proposta que existe — pior que a linha suja que se quer evitar. Todo
critério abaixo é de evidência forte (identificador fabricado pela coleta,
registro sem nada que o identifique, texto de erro de HTTP/browser no lugar do
conteúdo), nunca heurística de "parece pobre".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..schemas.proposta import PropostaCanonica

MOTIVO_ID_SINTETICO = "identificador fabricado pela coleta, não veio da fonte"
MOTIVO_SEM_CONTEUDO = "registro sem nada que identifique a proposta"
MOTIVO_RUIDO = "texto de falha de coleta no lugar do conteúdo"

#: prefixos de `id_externo` que a própria coleta inventa quando não achou o
#: identificador da fonte. Nenhum deles é número de proposta/convênio: são
#: nomes de etapa do pipeline ("scrape-2611606", "painel-3550308-0").
_ID_SINTETICO = re.compile(
    r"^(scrape|scraping|crawl4ai|firecrawl|playwright|painel|erro|error|none|null|undefined)"
    r"([-_].*)?$",
    re.IGNORECASE,
)

#: valores que a fonte (ou o parser) devolve no lugar de "vazio".
_PLACEHOLDERS = frozenset(
    {
        "",
        "-",
        "--",
        "---",
        "n/a",
        "na",
        "nao informado",
        "nao informada",
        "sem informacao",
        "null",
        "none",
        "nan",
        "undefined",
        "0",
    }
)

#: marcas de página de erro / bloqueio / HTML cru no lugar do conteúdo. Todas
#: são frases que não existem em nome de programa ou objeto de convênio — o
#: casamento é sobre o texto sem acento e em minúsculas.
_RUIDO = tuple(
    re.compile(p)
    for p in (
        r"\bscrap(e|ing)\b",
        r"^(erro|error)\b",
        r"\b(40[1349]|50[0234])\s+(forbidden|not found|unauthorized|error|"
        r"internal server error|bad gateway|service unavailable|gateway timeout)\b",
        r"\b(forbidden|unauthorized|access denied|acesso negado)\b",
        r"\b(page|pagina) (not found|nao encontrada)\b",
        r"\bnot found\b",
        r"\b(enable|habilit[ea]).{0,12}javascript\b",
        r"\bjavascript (is )?(required|disabled|desabilitado)\b",
        r"\bjust a moment\b",
        r"\bchecking your browser\b",
        r"\bcloudflare\b",
        r"\bservi[cç]o (temporariamente )?indisponivel\b",
        r"\bservice unavailable\b",
        r"\b(bad gateway|gateway time ?out)\b",
        r"\b(erro|falha) ao (carregar|processar|exibir|consultar)\b",
        r"\bnao foi possivel (carregar|processar|exibir|consultar|obter)\b",
        r"\btente novamente mais tarde\b",
        r"\bsess(ao|ion) (expirada|expired)\b",
        r"<\s*(html|body|div|span|table|script|iframe)\b",
        r'^\s*\{\s*"?(error|erro|message|detail)\b',
    )
)


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados — a forma que os padrões leem."""
    sem_acento = unicodedata.normalize("NFD", texto)
    limpo = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", limpo).strip().lower()


def _util(valor: str | None) -> bool:
    """O texto diz alguma coisa? (placeholder da fonte não conta como conteúdo)"""
    if not valor:
        return False
    normalizado = _normalizar(str(valor))
    return len(normalizado) >= 2 and normalizado not in _PLACEHOLDERS


def _tem_identidade(p: PropostaCanonica) -> bool:
    """A proposta se identifica? Nome/objeto ou número — valor sozinho não basta.

    Linha de TOTAL de tabela chega assim: valor preenchido e nada mais. Ela não
    é uma proposta, é o rodapé da página que o parser leu como registro.
    """
    return bool(
        _util(p.titulo)
        or _util(p.objeto)
        or _util(p.numero_proposta)
        or _util(p.numero_plano_trabalho)
    )


def _ruido(valor: str | None) -> bool:
    if not valor:
        return False
    normalizado = _normalizar(str(valor))
    return any(padrao.search(normalizado) for padrao in _RUIDO)


def motivo_rejeicao(p: PropostaCanonica) -> str | None:
    """Por que esta proposta NÃO pode entrar no cache — ou None se pode."""
    if not str(p.id_externo or "").strip() or _ID_SINTETICO.match(str(p.id_externo).strip()):
        return MOTIVO_ID_SINTETICO
    if not _tem_identidade(p):
        return MOTIVO_SEM_CONTEUDO
    # o ruído é checado nos campos DESCRITIVOS (os que o gestor lê como nome da
    # proposta). `situacao` fica de fora de propósito: "Erro na prestação de
    # contas" é situação legítima da fonte, não falha de coleta.
    if _ruido(p.titulo) or _ruido(p.objeto):
        return MOTIVO_RUIDO
    return None


@dataclass(frozen=True)
class Triagem:
    """O que passou na porta e o que ficou de fora (com o motivo, para o log)."""

    aceitas: list[PropostaCanonica]
    descartes: list[tuple[str, str]]  # (id_externo, motivo)

    @property
    def houve_descarte(self) -> bool:
        return bool(self.descartes)


def triar(canonicas: list[PropostaCanonica]) -> Triagem:
    """Separa as propostas gravaveis das que são resíduo de coleta."""
    aceitas: list[PropostaCanonica] = []
    descartes: list[tuple[str, str]] = []
    for canonica in canonicas:
        motivo = motivo_rejeicao(canonica)
        if motivo is None:
            aceitas.append(canonica)
        else:
            descartes.append((str(canonica.id_externo or "?"), motivo))
    return Triagem(aceitas=aceitas, descartes=descartes)


def resumo_descartes(descartes: list[tuple[str, str]]) -> str:
    """Uma linha para `sync_runs.erro` — quantos caíram e por quê.

    A coleta que descarta registro é `degradado`, não `ok`: o gestor precisa
    conseguir distinguir "a fonte não tem nada" de "a fonte respondeu lixo".
    """
    if not descartes:
        return ""
    por_motivo: dict[str, int] = {}
    for _, motivo in descartes:
        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
    detalhe = "; ".join(f"{motivo} ({n})" for motivo, n in sorted(por_motivo.items()))
    return f"{len(descartes)} registro(s) descartado(s) na triagem: {detalhe}"
