"""Exportação de PDF de proposta."""

from __future__ import annotations

from sqlalchemy import select

from src.db.session import rls_session
from src.models.proposta import Proposta
from src.services import pdf


async def test_gerar_pdf_proposta(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("pdf@pdf.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("fns", "P1", "3550308", "Ampliação de UBS")
    async with rls_session(u) as s:
        p = (await s.execute(select(Proposta))).scalars().first()
        conteudo = pdf.gerar_pdf_proposta(p)
    assert conteudo[:5] == b"%PDF-"  # é um PDF válido
    assert len(conteudo) > 500
