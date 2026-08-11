"""Exportação de proposta em PDF (reportlab)."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models.proposta import NATUREZAS_JURIDICAS, Proposta


def gerar_pdf_proposta(p: Proposta) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Proposta {p.id_externo}")
    styles = getSampleStyleSheet()
    elems = [
        Paragraph("Hub Capture — Proposta", styles["Title"]),
        Paragraph(p.titulo or "(sem título)", styles["Heading2"]),
        Spacer(1, 12),
    ]
    linhas = [
        ("Fonte", p.fonte),
        ("Nº proposta", p.numero_proposta or p.id_externo),
        ("Órgão", p.orgao_superior or "—"),
        ("Modalidade", p.modalidade or "—"),
        ("Natureza jurídica", NATUREZAS_JURIDICAS.get(p.natureza_juridica or "", "—")),
        ("Município (IBGE)", p.municipio_ibge or "—"),
        ("UF", p.uf or "—"),
        ("Valor total", f"R$ {p.valor_total}" if p.valor_total is not None else "—"),
        ("Contrapartida", f"R$ {p.contrapartida}" if p.contrapartida is not None else "—"),
        ("Situação", p.situacao or "—"),
        ("Emenda", p.emenda or "—"),
        ("Atualização fonte", str(p.data_atualizacao_fonte or "—")),
    ]
    tabela = Table([[k, str(v)] for k, v in linhas], colWidths=[140, 340])
    tabela.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elems.append(tabela)
    if p.resumo_ia:
        elems += [Spacer(1, 14), Paragraph("Resumo (IA)", styles["Heading3"]),
                  Paragraph(p.resumo_ia, styles["BodyText"])]
    doc.build(elems)
    return buf.getvalue()
