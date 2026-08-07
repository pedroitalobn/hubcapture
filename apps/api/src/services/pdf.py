"""Exportação de proposta em PDF (reportlab).

A hierarquia do documento espelha a do header da tela (seção 23 do CLAUDE.md):
MUNICÍPIO primeiro (pelo nome, com o IBGE como dado secundário), depois o objeto
da proposta, depois os números fortes — valor e EMPENHO, que é o que diz se o
recurso saiu do papel. Identificadores da fonte (nº da proposta, id externo)
fecham o documento, em "Identificação"; nunca o abrem.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models.proposta import Proposta
from .municipios import rotulo, uf_do_ibge

_CINZA = colors.HexColor("#6b7280")
_BORDA = colors.HexColor("#dddddd")
_FUNDO = colors.HexColor("#f3f4f6")


def _dec(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _brl(v: Any) -> str:
    d = _dec(v)
    if d is None:
        return "—"
    return "R$ " + f"{d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _tabela(linhas: list[tuple[str, str]], *, largura_rotulo: int = 140) -> Table:
    t = Table(
        [[k, v] for k, v in linhas], colWidths=[largura_rotulo, 480 - largura_rotulo]
    )
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDA),
                ("BACKGROUND", (0, 0), (0, -1), _FUNDO),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def _bloco_empenho(execucao: dict, styles) -> list:
    """Execução financeira (TransfereGov): empenhado, liberado, pago e o saldo
    empenhado ainda por utilizar — o número que move a ação do gestor."""
    empenhado = _dec(execucao.get("valor_empenhado")) or Decimal(0)
    pago = _dec(execucao.get("valor_pago")) or Decimal(0)
    a_utilizar = max(Decimal(0), empenhado - pago)
    return [
        Paragraph("Empenho e execução", styles["Heading3"]),
        _tabela(
            [
                ("Valor empenhado", _brl(execucao.get("valor_empenhado"))),
                ("Empenhado a utilizar", _brl(a_utilizar)),
                ("Valor liberado", _brl(execucao.get("valor_liberado"))),
                ("Valor pago", _brl(execucao.get("valor_pago"))),
                ("Valor global", _brl(execucao.get("valor_global"))),
                ("Saldo em conta", _brl(execucao.get("saldo_conta"))),
            ]
        ),
    ]


def gerar_pdf_proposta(
    p: Proposta, *, municipio_nome: str | None = None, uf: str | None = None
) -> bytes:
    """`municipio_nome`/`uf` cobrem o caso do cache sem nome (ver
    `services.municipios`) — o PDF nunca deve abrir com um código solto."""
    buf = BytesIO()
    nome = municipio_nome or p.municipio_nome
    sigla = uf or p.uf or uf_do_ibge(p.municipio_ibge)
    municipio = rotulo(nome, sigla, p.municipio_ibge)

    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{municipio} — proposta")
    styles = getSampleStyleSheet()
    sobretitulo = ParagraphStyle(
        "Sobretitulo", parent=styles["Normal"], fontSize=8, textColor=_CINZA,
        spaceAfter=2, leading=10,
    )
    secundario = ParagraphStyle(
        "Secundario", parent=styles["Normal"], fontSize=9, textColor=_CINZA, spaceAfter=10
    )

    # ── Header: município em primeiro lugar; o código IBGE é apoio ──────────
    apoio = " · ".join(
        x
        for x in (
            f"IBGE {p.municipio_ibge}" if p.municipio_ibge else None,
            f"UF {sigla}" if sigla else None,
            f"Fonte {p.fonte}",
        )
        if x
    )
    execucao = p.execucao if isinstance(p.execucao, dict) else {}
    elems: list = [
        Paragraph("HUB CAPTURE · CAPTAÇÃO", sobretitulo),
        Paragraph(municipio, styles["Title"]),
        Paragraph(apoio, secundario),
        Paragraph(p.titulo or p.objeto or "(sem título)", styles["Heading2"]),
        Spacer(1, 8),
        _tabela(
            [
                ("Valor total", _brl(p.valor_total)),
                ("Valor empenhado", _brl(execucao.get("valor_empenhado"))),
                ("Situação", p.situacao or "—"),
            ]
        ),
        Spacer(1, 14),
    ]

    if execucao:
        elems += _bloco_empenho(execucao, styles)
        elems.append(Spacer(1, 14))

    elems += [
        Paragraph("Detalhes", styles["Heading3"]),
        _tabela(
            [
                ("Órgão", p.orgao_superior or "—"),
                ("Modalidade", p.modalidade or "—"),
                ("Contrapartida", _brl(p.contrapartida)),
                ("Emenda", p.emenda or "—"),
                ("Atualização fonte", str(p.data_atualizacao_fonte or "—")),
            ]
        ),
    ]

    if p.resumo_ia:
        elems += [
            Spacer(1, 14),
            Paragraph("Resumo (IA)", styles["Heading3"]),
            Paragraph(p.resumo_ia, styles["BodyText"]),
        ]

    # ── Identificadores: dado secundário, fecham o documento ───────────────
    elems += [
        Spacer(1, 14),
        Paragraph("Identificação", styles["Heading3"]),
        _tabela(
            [
                ("Nº da proposta", p.numero_proposta or "—"),
                ("ID na fonte", p.id_externo),
                ("Fonte", p.fonte),
            ]
        ),
    ]

    doc.build(elems)
    return buf.getvalue()
