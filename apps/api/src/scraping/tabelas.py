"""Tabela renderizada → registros no formato do schema do connector.

Camada comum aos providers de scraping local. Duas responsabilidades:

1. **Ler tabela de HTML** (`linhas_de_html`) — tanto `<table>/<tr>/<td>` quanto
   **grid ARIA** (`role="grid"`, `role="row"`, `role="columnheader"`), que é como
   o Qlik do painel da Visão Geral do TransfereGov monta a listagem. Sem isso o
   Crawl4AI enxerga zero linha na página que mais interessa.
2. **Casar cabeçalho com campo** (`mapear`) — o connector já declara um JSON
   Schema; aqui o cabeçalho "Valor Empenhado" encontra `valor_empenhado` e
   "Nº Transferência" encontra `numero` pela `description` declarada. Sem LLM:
   é comparação de texto normalizado, determinística e sem custo por página.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from typing import Any

CELULAS = {"td", "th"}
PAPEIS_CELULA = {"columnheader", "gridcell", "cell", "rowheader"}
PAPEIS_LINHA = {"row"}
PAPEIS_TABELA = {"grid", "table", "treegrid"}


def norm(texto: str) -> str:
    """Minúsculo, sem acento e sem pontuação — base de toda comparação aqui."""
    sem_acento = unicodedata.normalize("NFD", texto or "")
    limpo = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", limpo.lower()).strip()


#: tags sem fechamento — não entram na pilha, senão desalinham tudo
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _LeitorTabelas(HTMLParser):
    """Varre o HTML acumulando linhas de tabela/grid, sem dependência externa.

    Mantém uma PILHA de elementos abertos, cada um marcado como tabela, linha,
    célula ou nada. É o que faz o grid ARIA funcionar: ali tabela, linha e célula
    são todas `<div>`, então fechar no primeiro `</div>` encerraria o grid na
    primeira célula. Fechando pela pilha, cada `</div>` fecha exatamente o
    elemento que abriu.

    Tolerante a HTML real: `</div>` sobrando é ignorado e tag não fechada é
    encerrada junto com o ancestral (desempilha até casar a tag).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabelas: list[list[list[str]]] = []
        self._pilha: list[dict[str, Any]] = []

    @staticmethod
    def _papel(attrs: list[tuple[str, str | None]]) -> str:
        return next((v or "" for k, v in attrs if k == "role"), "").lower()

    def _tipo(self, tag: str, papel: str) -> str | None:
        if tag == "table" or papel in PAPEIS_TABELA:
            return "tabela"
        if tag == "tr" or papel in PAPEIS_LINHA:
            return "linha"
        if tag in CELULAS or papel in PAPEIS_CELULA:
            return "celula"
        return None

    def _quadro_atual(self, tipo: str) -> dict[str, Any] | None:
        for quadro in reversed(self._pilha):
            if quadro["tipo"] == tipo:
                return quadro
            if quadro["tipo"] == "tabela":  # não vaza para a tabela de fora
                return None
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        tipo = self._tipo(tag, self._papel(attrs))
        quadro: dict[str, Any] = {"tag": tag, "tipo": tipo}
        if tipo == "tabela":
            quadro["linhas"] = []
        elif tipo == "linha":
            quadro["celulas"] = []
        elif tipo == "celula":
            quadro["texto"] = []
        self._pilha.append(quadro)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return  # <div/> não abre contexto

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        # desempilha até (e incluindo) a tag que fecha; tag órfã não faz nada
        if not any(q["tag"] == tag for q in self._pilha):
            return
        while self._pilha:
            quadro = self._pilha.pop()
            self._encerrar(quadro)
            if quadro["tag"] == tag:
                return

    def handle_data(self, data: str) -> None:
        celula = self._quadro_atual("celula")
        if celula is not None:
            celula["texto"].append(data)

    def _encerrar(self, quadro: dict[str, Any]) -> None:
        tipo = quadro["tipo"]
        if tipo == "celula":
            texto = re.sub(r"\s+", " ", "".join(quadro["texto"])).strip()
            linha = self._quadro_atual("linha")
            if linha is not None:
                linha["celulas"].append(texto)
        elif tipo == "linha":
            tabela = self._quadro_atual("tabela")
            if tabela is not None and quadro["celulas"]:
                tabela["linhas"].append(quadro["celulas"])
        elif tipo == "tabela" and quadro["linhas"]:
            self.tabelas.append(quadro["linhas"])


def linhas_de_html(html: str) -> list[list[dict[str, str]]]:
    """HTML → tabelas, cada uma como lista de {cabeçalho: célula}."""
    leitor = _LeitorTabelas()
    try:
        leitor.feed(html or "")
        leitor.close()
    except Exception:
        return []
    saida = []
    for tabela in leitor.tabelas:
        registros = _para_registros(tabela)
        if registros:
            saida.append(registros)
    return saida


def _para_registros(tabela: list[list[str]]) -> list[dict[str, str]]:
    """Primeira linha vira cabeçalho; as demais viram registros."""
    if len(tabela) < 2:
        return []
    cabecalhos = tabela[0]
    if not any(c.strip() for c in cabecalhos):
        return []
    registros = []
    for linha in tabela[1:]:
        if not any(c.strip() for c in linha):
            continue
        registros.append(
            {
                (cabecalhos[i] if i < len(cabecalhos) and cabecalhos[i] else f"col_{i}"): valor
                for i, valor in enumerate(linha)
            }
        )
    return registros


def maior_tabela(tabelas: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    """A tabela de dados é a maior da página (as outras são filtro/cabeçalho)."""
    return max(tabelas, key=len) if tabelas else []


def alvo_do_schema(schema: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Primeira propriedade array-de-objetos do schema + as propriedades do item."""
    for chave, prop in (schema.get("properties") or {}).items():
        if prop.get("type") == "array":
            return chave, (prop.get("items") or {}).get("properties") or {}
    return None, {}


def mapear(linha: dict[str, str], campos: dict[str, Any]) -> dict[str, Any]:
    """Casa cabeçalho da tabela com campo do schema (nome ou `description`).

    Sem correspondência exata, aceita contido-em: "Valor Empenhado" casa com
    `valor_empenhado`, e `numero` casa com "Nº Transferência" pela description.
    O que não casou fica em `_linha`, para calibrar a fonte depois sem perder dado.
    """
    if not campos:
        return dict(linha)
    normalizadas = {norm(k): v for k, v in linha.items()}
    saida: dict[str, Any] = {}
    for campo, spec in campos.items():
        alvos = [norm(campo)]
        if isinstance(spec, dict) and spec.get("description"):
            alvos.append(norm(str(spec["description"])))
        valor = next((normalizadas[a] for a in alvos if a in normalizadas), None)
        if valor is None:
            for alvo in alvos:
                achado = next(
                    (v for k, v in normalizadas.items() if alvo and (alvo in k or k in alvo)),
                    None,
                )
                if achado is not None:
                    valor = achado
                    break
        if valor is not None:
            saida[campo] = valor
    saida.setdefault("_linha", linha)
    return saida


__all__ = ["alvo_do_schema", "linhas_de_html", "maior_tabela", "mapear", "norm"]
