"""Espelho da proposta em PDF — o documento que o gestor compartilha.

O gestor precisa mandar a proposta para o gabinete, para a secretaria ou para o
WhatsApp de quem decide, e o que ele mandava era uma tabela cinza de 11 linhas.
O **espelho** é o mesmo conteúdo da tela de detalhe, diagramado com a identidade
do Hub Capture: banda da marca, faixa de destaque (valor + empenho + safra),
barra de execução financeira, prazos, pendências, o ANDAMENTO (pareceres e
marcos da tramitação), os EMPENHOS e a EMENDA que banca a proposta. Um só
clique, um só arquivo, pronto para circular fora do painel.

**O documento é do gestor, não da plataforma.** Nada de plumbing aqui: sem
proveniência campo a campo, sem identificador de integração, sem dump do
registro bruto, sem nome de fonte de dados e sem instrução de administração. O
que o espelho carrega é o que quem decide precisa ler.

**Fontes tipográficas**: só as Type1 embutidas no reportlab (Helvetica/Courier).
A imagem da API é `python:3.12-slim`, que não traz nenhuma TTF — usar Inter
Tight/Roboto Mono exigiria embarcar os arquivos no repositório. O sistema
tipográfico do design é reproduzido com o que há: peso, tamanho, caixa e
`charSpace` (é o que dá a voz de "rótulo técnico" ao lugar do mono).

**Paleta**: os tokens do tema CLARO de `apps/web/app/globals.css`. Papel é
branco; o espelho é impresso e reencaminhado, então nunca segue o tema escuro.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..models.proposta import Proposta
from .municipios import rotulo as rotulo_municipio
from .texto import humanizar_caixa

# ── Paleta (tema claro do design system) ────────────────────────────────────
LIME = HexColor("#cef79e")  # acento primário da marca
AQUA = HexColor("#8be0d4")  # acento secundário (gradientes)
ABYSS = HexColor("#222f30")  # tinta / banda da marca
INK = HexColor("#222f30")
INK_2 = HexColor("#46504f")
INK_3 = HexColor("#7f8a80")  # metadata
HAIRLINE = HexColor("#c9cbbe")
SURFACE = HexColor("#f7f7f5")
SURFACE_2 = HexColor("#e7e8e1")
CARD = HexColor("#ffffff")
OK = HexColor("#2f6b4f")
OK_BG = HexColor("#eaf1ed")
WARN = HexColor("#8a6a1f")
WARN_BG = HexColor("#f5eeda")
DANGER = HexColor("#9b3f2c")
DANGER_BG = HexColor("#f6e6e0")
BAR_1 = HexColor("#d3e8c6")  # empenhado
BAR_2 = HexColor("#86bd76")  # liberado
BAR_3 = HexColor("#2f6b4f")  # pago

TONS: dict[str, tuple[Color, Color]] = {  # tom → (texto, fundo)
    "ok": (OK, OK_BG),
    "warn": (WARN, WARN_BG),
    "danger": (DANGER, DANGER_BG),
    "neutral": (INK_2, SURFACE_2),
}

# ── Geometria ───────────────────────────────────────────────────────────────
LARGURA, ALTURA = A4
MARGEM = 36.0
BANDA_CAPA = 76.0  # banda da marca na primeira página
BANDA_INTERNA = 38.0  # banda enxuta nas seguintes
RODAPE = 44.0
UTIL = LARGURA - 2 * MARGEM
PAD_CARD = 13.0
GAP = 14.0
MEIO = (UTIL - GAP) / 2

SANS = "Helvetica"
SANS_BOLD = "Helvetica-Bold"

# ── Estilos ─────────────────────────────────────────────────────────────────


def _estilo(nome: str, **kw: Any) -> ParagraphStyle:
    base = dict(fontName=SANS, fontSize=9.5, leading=13.5, textColor=INK)
    base.update(kw)
    return ParagraphStyle(nome, **base)


# `label-mono` do design: caixa alta, corpo pequeno, tracking positivo.
ROTULO = _estilo("rotulo", fontSize=7, leading=9.5, textColor=INK_2, charSpace=0.75)
ROTULO_CLARO = _estilo("rotulo_claro", parent=ROTULO, textColor=INK_3)
SECAO = _estilo("secao", fontSize=7.6, leading=10, textColor=INK_3, charSpace=1.0)
TITULO = _estilo("titulo", fontName=SANS_BOLD, fontSize=17, leading=20.5)
META = _estilo("meta", fontSize=9, leading=12.5, textColor=INK_2)
CORPO = _estilo("corpo", fontSize=9.2, leading=13.6, textColor=INK_2)
VALOR = _estilo("valor", fontSize=9.5, leading=12.6)
VALOR_LG = _estilo("valor_lg", fontName=SANS_BOLD, fontSize=11.5, leading=14)
VALOR_HERO = _estilo("valor_hero", fontName=SANS_BOLD, fontSize=19, leading=21.5)
DIREITA = _estilo("direita", alignment=TA_RIGHT)
PEQUENO = _estilo("pequeno", fontSize=7.6, leading=10.6, textColor=INK_3)


# ── Formatação de dado ──────────────────────────────────────────────────────


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _brl(v: Any, vazio: str = "—") -> str:
    """R$ 1.234.567,89 — sem depender de locale instalado no container."""
    n = _dec(v)
    if n is None:
        return vazio
    inteiro, _, centavos = f"{n:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _data_iso(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _data(v: Any, vazio: str = "—") -> str:
    d = _data_iso(v)
    return d.strftime("%d/%m/%Y") if d else vazio


def _dias_ate(v: Any) -> int | None:
    d = _data_iso(v)
    return (d - date.today()).days if d else None


def _prazo_label(dias: int | None) -> str:
    if dias is None:
        return ""
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanhã"
    if dias > 0:
        return f"vence em {dias} dias"
    if dias == -1:
        return "venceu ontem"
    return f"vencido há {abs(dias)} dias"


def _tom_prazo(dias: int | None) -> str | None:
    """Mesma escada da tela (`lib/format.ts::tomPrazo`) — uma regra só no app."""
    if dias is None:
        return None
    if dias <= 7:
        return "danger"
    if dias <= 30:
        return "warn"
    return "ok"


def _tom_situacao(situacao: str | None) -> str:
    s = (situacao or "").lower()
    if re.search(r"aprovad|celebrad|vigente|conclu|execu|pago|libera", s):
        return "ok"
    if re.search(r"pendenc|analise|análise|aguardand|diligenc|cadastr", s):
        return "warn"
    if re.search(r"rejeitad|cancelad|impedid|arquivad|indefer|inadimpl", s):
        return "danger"
    return "neutral"


# Tetos de conteúdo — um card é UMA célula de tabela e não se parte entre
# páginas: sem teto, um `objeto` de 8 mil caracteres (ou 40 pendências) faz o
# reportlab abortar com LayoutError e a exportação inteira cai. Os números saem
# da largura de cada bloco (≈4,6pt por caractere a 9,2pt), com folga sobre os
# ~705pt úteis da página. Nenhum corte é silencioso: o texto sempre diz que
# foi abreviado.
_MAX_TITULO = 200  # título na largura cheia (17pt)
_MAX_CAMPO = 90  # valor de campo em célula de grade
_MAX_TEXTO = 1000  # objeto, movimentação, resumo
_MAX_ITENS_LISTA = 10  # prazos/pendências por card
_MAX_ITEM_LISTA = 100  # descrição de cada item da lista


def _recorte(texto: str, limite: int = _MAX_TEXTO, *, nota: bool = True) -> str:
    if len(texto) <= limite:
        return texto
    cortado = texto[:limite].rstrip()
    return f"{cortado}… (trecho abreviado)" if nota else f"{cortado}…"


def _hex(cor: Color) -> str:
    """`#rrggbb` para uso dentro do markup do Paragraph (que não aceita Color)."""
    return "#" + cor.hexval()[2:]


def _t(v: Any, vazio: str = "—", limite: int = _MAX_CAMPO) -> str:
    """Texto pronto para o Paragraph: humanizado, recortado e com XML escapado."""
    if v is None or v == "":
        return vazio
    return escape(_recorte(humanizar_caixa(v), limite, nota=False)) or vazio


# ── Primitivas de desenho ───────────────────────────────────────────────────


def _gradiente_marca(c: Canvas, x: float, y: float, largura: float, altura: float) -> None:
    """Preenche um retângulo com o `--grad-brand` (lime → aqua)."""
    c.saveState()
    caminho = c.beginPath()
    caminho.rect(x, y, largura, altura)
    c.clipPath(caminho, stroke=0)
    c.linearGradient(x, y, x + largura, y, (LIME, AQUA), extend=True)
    c.restoreState()


def _texto_espacado(
    c: Canvas,
    x: float,
    y: float,
    texto: str,
    *,
    fonte: str,
    tamanho: float,
    cor: Color,
    espaco: float,
    direita: bool = False,
) -> None:
    """Texto com tracking positivo — o `letter-spacing` dos rótulos do design.

    O canvas só expõe `charSpace` pelo objeto de texto, e com tracking a largura
    deixa de ser a do `stringWidth` (sobra um avanço por caractere): alinhar à
    direita exige recalcular a largura na mão.

    O `Tc` do PDF é estado GRÁFICO, não do bloco de texto: sem zerar no fim, o
    tracking da banda da marca vaza para todo o resto da página (o texto passa a
    ser desenhado mais largo do que foi medido no layout e transborda os cards).
    """
    if direita:
        x -= c.stringWidth(texto, fonte, tamanho) + espaco * (len(texto) - 1)
    c.saveState()
    objeto = c.beginText(x, y)
    objeto.setFont(fonte, tamanho)
    objeto.setCharSpace(espaco)
    objeto.setFillColor(cor)
    objeto.textOut(texto)
    objeto.setCharSpace(0)
    c.drawText(objeto)
    c.restoreState()


def _ponto_marca(c: Canvas, x: float, y: float, raio: float) -> None:
    """O `brand-dot`: o disco em gradiente que assina a marca."""
    c.saveState()
    caminho = c.beginPath()
    caminho.circle(x, y, raio)
    c.clipPath(caminho, stroke=0)
    c.linearGradient(x - raio, y, x + raio, y, (LIME, AQUA), extend=True)
    c.restoreState()


class FioGradiente(Flowable):
    """O fio lime→aqua do topo do card — assinatura quase subliminar do sistema."""

    def __init__(self, largura: float, altura: float = 2.0) -> None:
        super().__init__()
        self.largura, self.altura = largura, altura

    def wrap(self, *_: float) -> tuple[float, float]:
        return self.largura, self.altura

    def draw(self) -> None:
        _gradiente_marca(self.canv, 0, 0, self.largura, self.altura)


class Regua(Flowable):
    """Hairline horizontal (o `.hairline-rule` do design)."""

    def __init__(self, largura: float, cor: Color = HAIRLINE) -> None:
        super().__init__()
        self.largura, self.cor = largura, cor

    def wrap(self, *_: float) -> tuple[float, float]:
        return self.largura, 1

    def draw(self) -> None:
        self.canv.setStrokeColor(self.cor)
        self.canv.setLineWidth(0.6)
        self.canv.line(0, 0.5, self.largura, 0.5)


class Pilulas(Flowable):
    """Linha de pílulas que quebra sozinha (categorias, badges, proveniência).

    Cada item é `(texto, tom)`; tons vêm de `TONS`. Desenhado no canvas em vez
    de virar tabela porque pílula é forma arredondada com o texto centrado — em
    célula de tabela o alinhamento vertical nunca fecha.
    """

    FONTE = 7.4
    ALTURA_PILULA = 13.0
    ESPACO = 4.0

    def __init__(self, itens: list[tuple[str, Any]], largura: float) -> None:
        super().__init__()
        # `tom` é a chave de `TONS` ou um par (texto, fundo) explícito — a
        # legenda da barra de execução precisa das cores dos segmentos.
        self.itens = [(t, tom) for t, tom in itens if t]
        self.largura = largura
        self._linhas: list[list[tuple[str, str, float]]] = []

    def wrap(self, largura_disp: float, _altura: float) -> tuple[float, float]:
        self.largura = min(self.largura, largura_disp)
        self._linhas, linha, usado = [], [], 0.0
        for texto, tom in self.itens:
            largura_texto = self.canv.stringWidth(texto, SANS, self.FONTE) + 15
            if linha and usado + largura_texto > self.largura:
                self._linhas.append(linha)
                linha, usado = [], 0.0
            linha.append((texto, tom, largura_texto))
            usado += largura_texto + self.ESPACO
        if linha:
            self._linhas.append(linha)
        altura = len(self._linhas) * (self.ALTURA_PILULA + self.ESPACO) - self.ESPACO
        return self.largura, max(altura, 0)

    def draw(self) -> None:
        c = self.canv
        y = (len(self._linhas) - 1) * (self.ALTURA_PILULA + self.ESPACO)
        for linha in self._linhas:
            x = 0.0
            for texto, tom, largura in linha:
                cor_texto, cor_fundo = (
                    tom if isinstance(tom, tuple) else TONS.get(tom, TONS["neutral"])
                )
                c.setFillColor(cor_fundo)
                c.setStrokeColor(cor_texto)
                c.setLineWidth(0.4)
                c.roundRect(x, y, largura, self.ALTURA_PILULA, self.ALTURA_PILULA / 2, 1, 1)
                c.setFillColor(cor_texto)
                c.setFont(SANS, self.FONTE)
                c.drawString(x + 7.5, y + 4.1, texto)
                x += largura + self.ESPACO
            y -= self.ALTURA_PILULA + self.ESPACO


class BarraExecucao(Flowable):
    """Barra empilhada da execução: pago ⊂ liberado ⊂ empenhado sobre o global.

    A mesma leitura da tela de detalhe — os três segmentos partem da origem e se
    sobrepõem, então o mais avançado (pago) é sempre o mais escuro e mais curto.
    """

    ALTURA = 9.0

    def __init__(self, largura: float, valores: dict[str, Decimal | None]) -> None:
        super().__init__()
        self.largura = largura
        self.valores = valores

    def wrap(self, largura_disp: float, _altura: float) -> tuple[float, float]:
        self.largura = min(self.largura, largura_disp)
        return self.largura, self.ALTURA

    def draw(self) -> None:
        c = self.canv
        total = self.valores.get("global") or Decimal(0)
        c.setFillColor(SURFACE_2)
        c.roundRect(0, 0, self.largura, self.ALTURA, self.ALTURA / 2, 0, 1)
        if total <= 0:
            return
        for chave, cor in (("empenhado", BAR_1), ("liberado", BAR_2), ("pago", BAR_3)):
            valor = self.valores.get(chave) or Decimal(0)
            if valor <= 0:
                continue
            largura = min(float(valor / total), 1.0) * self.largura
            c.setFillColor(cor)
            c.roundRect(0, 0, max(largura, self.ALTURA), self.ALTURA, self.ALTURA / 2, 0, 1)


# ── Primitivas de layout ────────────────────────────────────────────────────


def _campo(rotulo: str, valor: str, *, tom: str | None = None, grande: bool = False) -> list:
    """Par rótulo/valor (o `.field` do design) — vai direto numa célula."""
    estilo = VALOR_LG if grande else VALOR
    if tom:
        estilo = _estilo("campo_tom", parent=estilo, textColor=TONS[tom][0])
    return [Paragraph(rotulo.upper(), ROTULO), Spacer(1, 1.5), Paragraph(valor, estilo)]


def _grade(campos: list[list], largura: float, colunas: int = 3) -> Table:
    """A `.data-grid`: campos alinhados em colunas reais, não em flex irregular."""
    linhas = [campos[i : i + colunas] for i in range(0, len(campos), colunas)]
    if linhas:
        linhas[-1] += [""] * (colunas - len(linhas[-1]))
    col = largura / colunas
    return Table(
        linhas or [[""]],
        colWidths=[col] * colunas,
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        ),
    )


def _card(
    conteudo: list,
    largura: float,
    *,
    titulo: str | None = None,
    fundo: Color = CARD,
    fio: bool = False,
) -> Table:
    """Superfície flutuante do design: cantos redondos, hairline e (às vezes)
    o fio de gradiente no topo. Um card = uma célula de tabela arredondada."""
    interno: list = []
    if fio:
        interno.append(FioGradiente(largura - 2 * PAD_CARD))
        interno.append(Spacer(1, 9))
    if titulo:
        interno.append(Paragraph(titulo.upper(), SECAO))
        interno.append(Spacer(1, 4))
        interno.append(Regua(largura - 2 * PAD_CARD))
        interno.append(Spacer(1, 8))
    interno += conteudo
    return Table(
        [[interno]],
        colWidths=[largura],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fundo),
                ("BOX", (0, 0), (-1, -1), 0.6, HAIRLINE),
                ("ROUNDEDCORNERS", [9, 9, 9, 9]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), PAD_CARD),
                ("RIGHTPADDING", (0, 0), (-1, -1), PAD_CARD),
                ("TOPPADDING", (0, 0), (-1, -1), PAD_CARD - 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), PAD_CARD - 2),
            ]
        ),
    )


def _lado_a_lado(esquerda: Table, direita: Table) -> Table:
    return Table(
        [[esquerda, direita]],
        colWidths=[MEIO, MEIO],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), GAP),
                ("LEFTPADDING", (1, 0), (1, -1), 0),
                ("RIGHTPADDING", (1, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def _lista_datada(itens: list[tuple[str, Any]], largura: float) -> list:
    """A `.data-row`: descrição à esquerda, data (com urgência) à direita."""
    if not itens:
        return [Paragraph("Nada registrado.", PEQUENO)]
    omitidos = max(0, len(itens) - _MAX_ITENS_LISTA)
    linhas = []
    for descricao, quando in itens[:_MAX_ITENS_LISTA]:
        dias = _dias_ate(quando)
        tom = _tom_prazo(dias)
        cor = TONS[tom][0] if tom else INK_3
        direita = _data(quando, "")
        rotulo = _prazo_label(dias)
        linhas.append(
            [
                Paragraph(_t(descricao, limite=_MAX_ITEM_LISTA), CORPO),
                Paragraph(
                    f"<font color='{_hex(cor)}'>{escape(direita)}"
                    + (f"<br/><font size='7'>{escape(rotulo)}</font>" if rotulo else "")
                    + "</font>",
                    DIREITA,
                ),
            ]
        )
    saida: list = [
        Table(
            linhas,
            colWidths=[largura * 0.62, largura * 0.38],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.5, HAIRLINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        )
    ]
    if omitidos:
        saida += [Spacer(1, 5), Paragraph(f"+ {omitidos} não exibidos neste espelho.", PEQUENO)]
    return saida


# ── Leitura da proposta ─────────────────────────────────────────────────────


def _prazos(p: Proposta) -> list[tuple[str, Any]]:
    saida = []
    for item in p.prazos or []:
        if isinstance(item, dict):
            saida.append((item.get("tipo") or "prazo", item.get("data_limite")))
    return saida


def _pendencias(p: Proposta) -> list[tuple[str, Any]]:
    saida = []
    for item in p.pendencias or []:
        if isinstance(item, dict):
            saida.append((item.get("descricao") or "—", item.get("prazo")))
    return saida


def _categorias(p: Proposta) -> list[str]:
    """Pílulas da curadoria; sem curadoria gravada, classifica na hora (como a API)."""
    from ..ai import categorias as categorias_ai

    slugs = p.categorias_ia or categorias_ai.classificar(
        p.titulo, p.objeto, p.orgao_superior, p.modalidade
    )
    return [c["rotulo"] for c in categorias_ai.rotular(slugs)]


def _titulo_proposta(p: Proposta) -> str:
    # Identificador NÃO é título (§35): sem título nem objeto, o espelho diz
    # isso — antes caía para `numero_proposta`/`id_externo` e o documento saía
    # encabeçado por um código.
    bruto = p.titulo or p.objeto or "Proposta sem título"
    return _recorte(humanizar_caixa(bruto), _MAX_TITULO, nota=False)


# ── Seções do espelho ───────────────────────────────────────────────────────


def _cabecalho(p: Proposta) -> list:
    from .propostas import classificar_tipo

    disponivel = classificar_tipo(p.situacao) == "disponivel"
    # Hierarquia do §35: o MUNICÍPIO encabeça o espelho (é a identidade do
    # registro), o objeto vem em seguida e os identificadores da fonte descem
    # para a linha de apoio. Antes a tarja era "FONTE · nº" e o município ia
    # junto do órgão, três degraus abaixo — e cru quando faltava o nome.
    territorio = rotulo_municipio(p.municipio_nome, p.uf, p.municipio_ibge)
    # Nº da proposta e data de criação são dado de cabeçalho: é por eles que o
    # gestor referencia a proposta e confere no portal da fonte.
    # sem NR_PROPOSTA não há referência: escrever "Proposta <id_externo>" daria
    # ao gestor um número para citar no órgão que a fonte não reconhece.
    referencia = f"Proposta {p.numero_proposta}" if p.numero_proposta else ""
    if p.data_proposta:
        referencia = f"{referencia} · de {_data(p.data_proposta)}".lstrip(" ·")
    # A FONTE DE DADOS saiu daqui: o espelho é o documento da proposta, não da
    # integração que a coletou. O que referencia a proposta é o número, a data e
    # o órgão concedente.
    meta = " · ".join(x for x in [referencia, _t(p.orgao_superior, "")] if x and x != "—")

    elementos: list = [
        Paragraph(escape(territorio), ROTULO_CLARO),
        Spacer(1, 5),
        Paragraph(escape(_titulo_proposta(p)), TITULO),
    ]
    if meta:
        elementos += [Spacer(1, 5), Paragraph(meta, META)]
    pilulas: list[tuple[str, Any]] = [
        (
            "Oportunidade disponível" if disponivel else "Proposta cadastrada",
            "ok" if disponivel else "neutral",
        )
    ]
    pilulas += [(c, "neutral") for c in _categorias(p)]
    elementos += [Spacer(1, 8), Pilulas(pilulas, UTIL)]
    return elementos


def _faixa_destaque(p: Proposta) -> Table:
    """O topo da hierarquia: valor total, EMPENHO e o ANO da proposta (a safra).

    O prazo de vencimento saiu daqui: vinha marcado errado com frequência (a
    retaguarda de vigência não é prazo de proposta) e continua no card "Prazos",
    onde é conferível item a item.

    O espelho é o espelho da TELA: EMPENHO traz o valor global da proposta
    (VL_GLOBAL_PROP na fonte), e o "Empenhado a utilizar" saiu daqui — era uma
    conta derivada (empenhado − pago) que nas propostas dava zero e nada dizia.
    """
    from .propostas import ano_de, valor_global_de

    # três colunas de peso igual no topo da faixa, com os gaps descontados
    interno = (UTIL - 2 * PAD_CARD - 2 * GAP) / 3
    valor_col: list = [
        Paragraph("VALOR TOTAL", ROTULO),
        Spacer(1, 3),
        Paragraph(_brl(p.valor_total), VALOR_HERO),
    ]
    if (_dec(p.contrapartida) or Decimal(0)) > 0:
        valor_col += [Spacer(1, 2), Paragraph(f"contrapartida {_brl(p.contrapartida)}", PEQUENO)]

    # EMPENHO: o valor global que a fonte publica para a proposta
    empenho_col: list = [
        Paragraph("EMPENHO", ROTULO),
        Spacer(1, 3),
        Paragraph(_brl(valor_global_de(p)), VALOR_HERO),
        Spacer(1, 2),
        Paragraph("valor global da proposta", PEQUENO),
    ]

    # ANO_PROP na fonte — a mesma safra que o filtro de ano usa
    ano = ano_de(p)
    ano_col: list = [
        Paragraph("ANO DA PROPOSTA", ROTULO),
        Spacer(1, 3),
        Paragraph(ano or "—", _estilo("hero_ano", parent=VALOR_HERO, textColor=INK)),
        Spacer(1, 2),
        Paragraph(
            f"criada em {_data(p.data_proposta)}" if p.data_proposta else "ano de criação",
            PEQUENO,
        ),
    ]

    topo = Table(
        [[valor_col, empenho_col, ano_col]],
        colWidths=[interno, interno, interno],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )

    pendentes = len(_pendencias(p))
    campos = [
        _campo("Situação", _t(p.situacao, "sem registro"), tom=_tom_situacao(p.situacao)),
        _campo("Modalidade", _t(p.modalidade)),
        _campo(
            "Pendências",
            "nenhuma" if pendentes == 0 else f"{pendentes} a resolver",
            tom="ok" if pendentes == 0 else "warn",
        ),
    ]

    conteudo = [
        topo,
        Spacer(1, 11),
        Regua(UTIL - 2 * PAD_CARD),
        Spacer(1, 8),
        _grade(campos, UTIL - 2 * PAD_CARD, colunas=min(len(campos), 4)),
    ]
    return _card(conteudo, UTIL, fundo=SURFACE, fio=True)


def _bloco_execucao(p: Proposta) -> list:
    """Execução financeira do TransfereGov — quanto chegou e quanto sobrou."""
    e = p.execucao or {}
    valores = {
        "global": _dec(e.get("valor_global")) or _dec(p.valor_total),
        "empenhado": _dec(e.get("valor_empenhado")),
        "liberado": _dec(e.get("valor_liberado")),
        "pago": _dec(e.get("valor_pago")),
    }
    interno = UTIL - 2 * PAD_CARD
    conteudo: list = [
        BarraExecucao(interno, valores),
        Spacer(1, 6),
        # Legenda com as cores dos próprios segmentos — sem isso a barra é uma
        # escada de verdes sem nome e o leitor não sabe onde termina o quê.
        Pilulas(
            [
                ("Empenhado", (INK_2, BAR_1)),
                ("Liberado", (INK, BAR_2)),
                ("Pago", (white, BAR_3)),
            ],
            interno,
        ),
        Spacer(1, 10),
        _grade(
            [
                _campo("Valor global", _brl(valores["global"]), grande=True),
                _campo("Empenhado", _brl(valores["empenhado"]), grande=True),
                _campo("Liberado", _brl(valores["liberado"])),
                _campo("Pago", _brl(valores["pago"])),
                _campo("Saldo em conta", _brl(e.get("saldo_conta"))),
            ],
            interno,
        ),
        Regua(interno),
        Spacer(1, 8),
        _grade(
            [
                _campo("Tipo de transferência", _t(e.get("tipo_transferencia"))),
                _campo("Ente recebedor", _t(e.get("ente_recebedor"))),
                _campo("Natureza jurídica", _t(e.get("natureza_juridica"))),
                _campo("Assinatura", _data(e.get("data_assinatura"))),
                _campo("Início da vigência", _data(e.get("data_inicio_vigencia"))),
                _campo(
                    "Fim da vigência",
                    _data(e.get("data_fim_vigencia")),
                    tom=_tom_prazo(_dias_ate(e.get("data_fim_vigencia"))),
                ),
            ],
            interno,
        ),
    ]
    ano = e.get("ano")
    titulo = "Execução financeira" + (f" ({ano})" if ano else "")
    return [_card(conteudo, UTIL, titulo=titulo)]


def _bloco_dados_gerais(p: Proposta) -> Table:
    interno = MEIO - 2 * PAD_CARD
    campos = [
        # município nomeado antes dos identificadores; o código IBGE vira um
        # campo próprio, rotulado (§35)
        _campo("Município", escape(rotulo_municipio(p.municipio_nome, p.uf, p.municipio_ibge))),
        _campo("Código IBGE", escape(str(p.municipio_ibge or "—"))),
        _campo("UF", escape(str(p.uf or "—"))),
        _campo("Órgão superior", _t(p.orgao_superior)),
        _campo("Modalidade", _t(p.modalidade)),
        _campo("Emenda", _t(p.emenda)),
        # SÓ o NR_PROPOSTA: cair para `id_externo` rotulava o identificador da
        # integração como "nº da proposta" — número que não existe no portal da
        # fonte, num documento feito para ser levado ao órgão.
        _campo("Nº da proposta", _t(p.numero_proposta)),
        _campo("Criada em", _data(p.data_proposta)),
        _campo("Última atualização", _data(p.data_atualizacao_fonte)),
    ]
    conteudo: list = [_grade(campos, interno, colunas=2)]
    if p.objeto:
        conteudo += [
            Regua(interno),
            Spacer(1, 8),
            Paragraph("OBJETO", ROTULO),
            Spacer(1, 3),
            Paragraph(_t(_recorte(str(p.objeto)), limite=_MAX_TEXTO + 60), CORPO),
        ]
    return _card(conteudo, MEIO, titulo="Dados gerais")


def _bloco_situacao(p: Proposta) -> Table:
    conteudo: list = [
        Paragraph("SITUAÇÃO", ROTULO),
        Spacer(1, 3),
        Paragraph(_t(p.situacao), VALOR_LG),
        Spacer(1, 10),
        Paragraph("ÚLTIMA MOVIMENTAÇÃO", ROTULO),
        Spacer(1, 3),
        Paragraph(
            _t(
                _recorte(str(p.movimentacao)) if p.movimentacao else None,
                "Sem movimentação registrada.",
                limite=_MAX_TEXTO + 60,
            ),
            CORPO,
        ),
    ]
    return _card(conteudo, MEIO, titulo="Situação e movimentação")


# ── Complementos: andamento, empenhos e emenda ──────────────────────────────
#
# O espelho é síncrono e só diagrama — quem lê o banco (e, quando o cache está
# vencido, a fonte) é o router, que entrega tudo pronto aqui. Sem isto o
# documento saía com a linha da proposta e nada da tramitação: o gestor via na
# tela o parecer, o empenho e o parlamentar autor, encaminhava o espelho e a
# outra ponta recebia um PDF sem nada daquilo.


@dataclass(slots=True)
class Complementos:
    """O que a tela de detalhe mostra além da linha da proposta."""

    andamento: list[Any] = field(default_factory=list)  # EventoAndamento
    empenhos: list[Any] = field(default_factory=list)  # EmpenhoRead
    resumo_empenhos: Any = None  # EmpenhoResumo
    emendas: list[Any] = field(default_factory=list)  # EmendaRead


# rótulo do passo — o mesmo do `TIPO_ROTULO` da linha do tempo no web
_TIPO_EVENTO = {
    "proposta": "Proposta",
    "parecer": "Parecer",
    "empenho": "Empenho",
    "vigencia": "Vigência",
    "prazo": "Prazo",
    "pendencia": "Pendência",
    "atualizacao": "Movimentação",
}

_MAX_EVENTOS = 24  # passos da tramitação no espelho
_EVENTOS_POR_CARD = 5
_MAX_TEXTO_EVENTO = 420  # texto do parecer dentro de um passo
_MAX_EMPENHOS = 18
_EMPENHOS_POR_CARD = 6
_MAX_EMENDAS = 8

EVENTO_TITULO = _estilo("evento_titulo", fontName=SANS_BOLD, fontSize=9.4, leading=12.8)


def _cor_do_tom(tom: Any) -> Color:
    return TONS.get(str(tom or "neutral"), TONS["neutral"])[0]


def _campo_direita(rotulo: str, valor: str) -> Paragraph:
    """Rótulo pequeno sobre o número, alinhado à direita da linha."""
    return Paragraph(
        f"<font size='7' color='{_hex(INK_3)}'>{escape(rotulo.upper())}</font><br/>{escape(valor)}",
        DIREITA,
    )


def _cards_de_linhas(
    linhas: list[list],
    *,
    titulo: str,
    por_card: int,
    proporcoes: tuple[float, float],
    cabecalho: list | None = None,
    nota: str | None = None,
) -> list:
    """Lista longa em cards de poucas linhas.

    Um card é UMA célula de tabela e não se parte entre páginas: 24 passos num
    card só derrubariam a geração inteira com LayoutError (mesma disciplina dos
    tetos de conteúdo acima). O fluxo empurra o card seguinte para a próxima
    página quando não cabe.
    """
    interno = UTIL - 2 * PAD_CARD
    estilo = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, HAIRLINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 10),
            ("RIGHTPADDING", (1, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
    )
    # Distribui as linhas por igual entre os cards: com o corte cru, 6 passos
    # em cards de 5 deixariam um card órfão de uma linha só no fim.
    cards = max(1, math.ceil(len(linhas) / por_card))
    por_card = math.ceil(len(linhas) / cards)

    partes: list = []
    for inicio in range(0, len(linhas), por_card):
        primeiro = inicio == 0
        conteudo: list = []
        if primeiro and cabecalho:
            conteudo += cabecalho + [Spacer(1, 8)]
        conteudo.append(
            Table(
                linhas[inicio : inicio + por_card],
                colWidths=[interno * proporcoes[0], interno * proporcoes[1]],
                style=estilo,
            )
        )
        if not primeiro:
            partes.append(Spacer(1, 8))
        partes.append(_card(conteudo, UTIL, titulo=titulo if primeiro else None))
    if nota:
        partes += [Spacer(1, 6), Paragraph(escape(nota), PEQUENO)]
    return partes


def _linha_andamento(ev: Any) -> list:
    """Um passo da tramitação: quando · o que é | o que aconteceu."""
    tipo = str(getattr(ev, "tipo", "") or "")
    rotulo = _TIPO_EVENTO.get(tipo, tipo.capitalize() or "Passo")
    if getattr(ev, "futuro", False):
        rotulo = f"{rotulo} · a vencer"
    esquerda = [
        Paragraph(escape(_data(getattr(ev, "data", None), "sem data")), VALOR),
        Spacer(1, 2),
        Paragraph(escape(rotulo.upper()), ROTULO_CLARO),
    ]

    cor = _cor_do_tom(getattr(ev, "tom", None))
    titulo = _t(getattr(ev, "titulo", None), "—", limite=_MAX_ITEM_LISTA)
    direita: list = [Paragraph(f"<font color='{_hex(cor)}'>{titulo}</font>", EVENTO_TITULO)]
    valor = _dec(getattr(ev, "valor", None))
    if valor and valor > 0:
        direita += [Spacer(1, 2), Paragraph(_brl(valor), VALOR)]
    ator = getattr(ev, "ator", None)
    if ator:
        direita += [Spacer(1, 2), Paragraph(_t(ator, limite=_MAX_ITEM_LISTA), CORPO)]
    detalhe = getattr(ev, "detalhe", None)
    if detalhe:
        direita += [Spacer(1, 1), Paragraph(_t(detalhe, limite=_MAX_ITEM_LISTA + 60), PEQUENO)]
    texto = getattr(ev, "texto", None)
    if texto:
        direita += [
            Spacer(1, 3),
            Paragraph(escape(_recorte(str(texto), _MAX_TEXTO_EVENTO)), PEQUENO),
        ]
    return [esquerda, direita]


def _bloco_andamento(eventos: list[Any]) -> list:
    if not eventos:
        return []
    omitidos = max(0, len(eventos) - _MAX_EVENTOS)
    return _cards_de_linhas(
        [_linha_andamento(ev) for ev in eventos[:_MAX_EVENTOS]],
        titulo="Andamento da proposta",
        por_card=_EVENTOS_POR_CARD,
        proporcoes=(0.24, 0.76),
        cabecalho=[
            Paragraph(
                "A tramitação em ordem — do mais recente para o mais antigo.",
                PEQUENO,
            )
        ],
        nota=f"+ {omitidos} passos mais antigos não exibidos neste espelho." if omitidos else None,
    )


def _linha_empenho(e: Any) -> list:
    """Um documento de empenho. O empenhado sai LÍQUIDO das anulações: um
    empenho devolvido que continuasse somando diria que há recurso onde não há."""
    anulado = _dec(getattr(e, "valor_anulado", None)) or Decimal(0)
    empenhado = (_dec(getattr(e, "valor_empenhado", None)) or Decimal(0)) - anulado
    marca = ""
    if anulado > 0:
        marca = "anulado em parte" if empenhado > 0 else "anulado"
    cabeca = " · ".join(
        x
        for x in [
            _data(getattr(e, "data_empenho", None), "sem data"),
            str(getattr(e, "numero_empenho", "") or ""),
            marca,
        ]
        if x
    )
    esquerda: list = [Paragraph(escape(cabeca), VALOR)]
    apoio = " · ".join(
        _t(x, "")
        for x in (
            getattr(e, "ug_emitente", None),
            getattr(e, "tipo_empenho", None),
            getattr(e, "natureza_despesa", None),
            getattr(e, "situacao", None),
        )
        if x
    )
    if apoio:
        esquerda += [Spacer(1, 2), Paragraph(apoio, PEQUENO)]

    direita: list = [_campo_direita("Empenhado", _brl(max(empenhado, Decimal(0))))]
    pago = _dec(getattr(e, "valor_pago", None)) or Decimal(0)
    if pago > 0:
        direita += [Spacer(1, 3), _campo_direita("Pago", _brl(pago))]
    return [esquerda, direita]


def _bloco_empenhos(itens: list[Any], resumo: Any) -> list:
    """Os documentos que reservaram o recurso no orçamento — saiu do papel?"""
    if not itens:
        return []
    interno = UTIL - 2 * PAD_CARD
    campos: list[list] = []
    if resumo is not None:
        campos = [
            _campo("Empenhado", _brl(getattr(resumo, "valor_empenhado", None)), grande=True),
            _campo("Pago", _brl(getattr(resumo, "valor_pago", None))),
        ]
        if (_dec(getattr(resumo, "valor_anulado", None)) or Decimal(0)) > 0:
            campos.append(
                _campo("Anulado", _brl(getattr(resumo, "valor_anulado", None)), tom="danger")
            )
        campos.append(_campo("Documentos", str(len(itens))))
    cabecalho = [_grade(campos, interno, colunas=min(len(campos), 4))] if campos else None

    omitidos = max(0, len(itens) - _MAX_EMPENHOS)
    return _cards_de_linhas(
        [_linha_empenho(e) for e in itens[:_MAX_EMPENHOS]],
        titulo="Empenhos",
        por_card=_EMPENHOS_POR_CARD,
        proporcoes=(0.62, 0.38),
        cabecalho=cabecalho,
        nota=f"+ {omitidos} empenhos não exibidos neste espelho." if omitidos else None,
    )


def _bloco_emendas(itens: list[Any]) -> list:
    """De quem é o dinheiro. O AUTOR lidera — é com o gabinete dele que se fala."""
    if not itens:
        return []
    linhas: list[list] = []
    for e in itens[:_MAX_EMENDAS]:
        nome = _t(getattr(e, "parlamentar", None), "Autor não informado")
        sigla = "/".join(
            str(x) for x in (getattr(e, "partido", None), getattr(e, "uf_parlamentar", None)) if x
        )
        esquerda: list = [Paragraph(f"{nome} ({escape(sigla)})" if sigla else nome, EVENTO_TITULO)]
        numero = getattr(e, "numero_emenda", None)
        ano = getattr(e, "ano", None)
        apoio = " · ".join(
            x
            for x in [
                f"emenda {escape(str(numero))}" if numero else "",
                str(ano) if ano else "",
                _t(getattr(e, "tipo_emenda", None), ""),
                _t(getattr(e, "cargo_parlamentar", None), ""),
                _t(getattr(e, "funcao", None), ""),
            ]
            if x
        )
        if apoio:
            esquerda += [Spacer(1, 2), Paragraph(apoio, PEQUENO)]

        direita: list = []
        for rotulo, bruto in (
            ("Valor", getattr(e, "valor", None)),
            ("Empenhado", getattr(e, "valor_empenhado", None)),
            ("Pago", getattr(e, "valor_pago", None)),
        ):
            if (_dec(bruto) or Decimal(0)) > 0:
                if direita:
                    direita.append(Spacer(1, 3))
                direita.append(_campo_direita(rotulo, _brl(bruto)))
        linhas.append([esquerda, direita or [Paragraph("", PEQUENO)]])

    omitidos = max(0, len(itens) - _MAX_EMENDAS)
    return _cards_de_linhas(
        linhas,
        titulo="Emenda parlamentar",
        por_card=_MAX_EMENDAS,
        proporcoes=(0.62, 0.38),
        nota=f"+ {omitidos} emendas não exibidas neste espelho." if omitidos else None,
    )


# ── Documento (banda da marca, rodapé, numeração) ───────────────────────────


class _CanvasNumerado(Canvas):
    """Duas passadas só para o rodapé saber o total de páginas ("2 de 5")."""

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self._paginas: list[dict] = []

    def showPage(self) -> None:
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._rodape_paginacao(total)
            super().showPage()
        super().save()

    def _rodape_paginacao(self, total: int) -> None:
        self.setFont(SANS, 7.2)
        self.setFillColor(INK_3)
        self.drawRightString(LARGURA - MARGEM, RODAPE - 22, f"{self._pageNumber} de {total}")


def _banda(c: Canvas, altura: float, subtitulo: str, capa: bool) -> None:
    """Banda da marca no topo: o Hub Capture assina o documento em toda página."""
    topo = ALTURA - altura
    c.setFillColor(ABYSS)
    c.rect(0, topo, LARGURA, altura, stroke=0, fill=1)
    _gradiente_marca(c, 0, topo - 2.4, LARGURA, 2.4)

    y_marca = topo + altura / 2 + (6 if capa else 0)
    _ponto_marca(c, MARGEM + 4, y_marca + 3.2, 4)
    _texto_espacado(
        c,
        MARGEM + 13,
        y_marca,
        "HUB CAPTURE",
        fonte=SANS_BOLD,
        tamanho=12 if capa else 10,
        cor=white,
        espaco=1.7,
    )
    _texto_espacado(
        c,
        LARGURA - MARGEM,
        y_marca + (2 if capa else 0),
        "ESPELHO DA PROPOSTA",
        fonte=SANS,
        tamanho=7.6 if capa else 7,
        cor=LIME,
        espaco=1.2,
        direita=True,
    )

    if subtitulo:
        c.setFillColor(HexColor("#9fb0ad"))
        c.setFont(SANS, 7.4)
        if capa:
            c.drawString(MARGEM + 13, topo + altura / 2 - 9, subtitulo)
        else:
            c.drawRightString(LARGURA - MARGEM, y_marca - 9, subtitulo)


def _rodape(c: Canvas, gerado_em: str) -> None:
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.6)
    c.line(MARGEM, RODAPE - 12, LARGURA - MARGEM, RODAPE - 12)
    c.setFillColor(INK_3)
    c.setFont(SANS, 7.2)
    c.drawString(MARGEM, RODAPE - 22, f"Hub Capture · espelho gerado em {gerado_em}")


def _montar_documento(buffer: BytesIO, p: Proposta, gerado_em: str) -> BaseDocTemplate:
    identidade = " · ".join(
        x
        for x in [
            f"Proposta {p.numero_proposta}" if p.numero_proposta else "",
            humanizar_caixa(p.municipio_nome or p.municipio_ibge or ""),
        ]
        if x
    )

    def capa(c: Canvas, _doc: BaseDocTemplate) -> None:
        _banda(c, BANDA_CAPA, f"Emitido em {gerado_em}", capa=True)
        _rodape(c, gerado_em)

    def interna(c: Canvas, _doc: BaseDocTemplate) -> None:
        _banda(c, BANDA_INTERNA, identidade, capa=False)
        _rodape(c, gerado_em)

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Espelho da proposta — {_titulo_proposta(p)}",
        author="Hub Capture",
        subject=identidade,
        creator="Hub Capture",
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=BANDA_CAPA,
        bottomMargin=RODAPE,
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="capa",
                frames=[
                    Frame(
                        MARGEM,
                        RODAPE,
                        UTIL,
                        ALTURA - BANDA_CAPA - RODAPE - 16,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=capa,
            ),
            PageTemplate(
                id="interna",
                frames=[
                    Frame(
                        MARGEM,
                        RODAPE,
                        UTIL,
                        ALTURA - BANDA_INTERNA - RODAPE - 12,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=interna,
            ),
        ]
    )
    return doc


def nome_arquivo(p: Proposta) -> str:
    """Nome legível para quem recebe o arquivo (some do Downloads menos fácil)."""
    partes = [
        "espelho",
        str(p.numero_proposta or p.id_externo or "proposta"),
        str(p.municipio_nome or p.municipio_ibge or ""),
    ]
    bruto = "-".join(x for x in partes if x)
    # "Mossoró" tem de virar "mossoro", não "mossor": sem transliterar, o
    # filtro de ASCII come a letra acentuada e o nome fica truncado.
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", bruto) if not unicodedata.combining(c)
    )
    limpo = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9\-]+", "-", sem_acento.lower())).strip("-")
    return f"{limpo[:80].strip('-') or 'espelho-proposta'}.pdf"


def gerar_pdf_proposta(
    p: Proposta,
    *,
    gerado_em: datetime | None = None,
    complementos: Complementos | None = None,
) -> bytes:
    """Espelho da proposta: uma peça pronta para circular fora do painel.

    `complementos` traz o andamento, os empenhos e a emenda já lidos pelo
    router — sem eles o documento sai só com a linha da proposta (é o que
    acontece em qualquer chamada que não tenha uma sessão de banco à mão).
    """
    momento = (gerado_em or datetime.now(UTC).astimezone()).strftime("%d/%m/%Y às %H:%M")
    extras = complementos or Complementos()
    buffer = BytesIO()
    doc = _montar_documento(buffer, p, momento)

    elementos: list = [NextPageTemplate("interna")]
    elementos += _cabecalho(p)
    elementos += [Spacer(1, 13), _faixa_destaque(p)]

    if p.resumo_ia:
        elementos += [
            Spacer(1, GAP),
            _card(
                [Paragraph(escape(_recorte(p.resumo_ia)), CORPO)],
                UTIL,
                titulo="Resumo da proposta",
            ),
        ]

    if p.execucao:
        elementos += [Spacer(1, GAP)] + _bloco_execucao(p)

    interno_meio = MEIO - 2 * PAD_CARD
    elementos += [
        Spacer(1, GAP),
        _lado_a_lado(
            _card(_lista_datada(_prazos(p), interno_meio), MEIO, titulo="Prazos"),
            _card(_lista_datada(_pendencias(p), interno_meio), MEIO, titulo="Pendências"),
        ),
        Spacer(1, GAP),
        _lado_a_lado(_bloco_dados_gerais(p), _bloco_situacao(p)),
    ]

    # Mesma ordem da tela de detalhe: andamento, empenhos e emenda.
    for bloco in (
        _bloco_andamento(extras.andamento),
        _bloco_empenhos(extras.empenhos, extras.resumo_empenhos),
        _bloco_emendas(extras.emendas),
    ):
        if bloco:
            elementos += [Spacer(1, GAP)] + bloco

    doc.build(elementos, canvasmaker=_CanvasNumerado)
    return buffer.getvalue()
