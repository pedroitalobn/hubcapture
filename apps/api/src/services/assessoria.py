"""Assessoria orçamentária — contatos que redirecionam para o WhatsApp.

O gestor tira dúvidas orçamentárias falando DIRETO com uma pessoa da
assessoria; a aba do painel só lista os contatos e abre o WhatsApp. A lista é
dado de NÍVEL-PLATAFORMA (igual para todos os tenants), editável pelo painel
admin em runtime — o padrão versionado abaixo vale enquanto ninguém gravou
nada no banco (mesma mecânica dos módulos da §29: uma chave em
`configuracoes`, sem migration).
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.configuracao import Configuracao

_CHAVE = "assessoria_contatos"
_CATEGORIA = "assessoria"

# Padrão versionado — vale até o admin gravar a própria lista pelo painel.
CONTATOS_PADRAO: list[dict] = [
    {"nome": "Raul", "telefone": "+55 61 98288-1163", "descricao": None},
    {"nome": "Josué", "telefone": "+55 61 98100-9698", "descricao": None},
    {"nome": "Diovany", "telefone": "+55 62 98282-3332", "descricao": None},
]


def whatsapp_url(telefone: str) -> str:
    """Link wa.me a partir do telefone exibido (só dígitos, com DDI do Brasil).

    O critério é o comprimento, não o prefixo: um número local do DDD 55 (RS)
    também começa com "55" e um startswith prefixaria errado.
    """
    digitos = re.sub(r"\D", "", telefone)
    if digitos and len(digitos) <= 11:  # DDD + número, sem DDI
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def _com_link(contatos: list[dict]) -> list[dict]:
    return [
        {
            "nome": (c.get("nome") or "").strip(),
            "telefone": (c.get("telefone") or "").strip(),
            "descricao": c.get("descricao") or None,
            "whatsapp_url": whatsapp_url(c.get("telefone") or ""),
        }
        for c in contatos
        if c.get("telefone")
    ]


async def listar(session: AsyncSession) -> list[dict]:
    """Lista efetiva (banco > padrão versionado), com o link wa.me pronto."""
    row = (
        await session.execute(select(Configuracao).where(Configuracao.chave == _CHAVE))
    ).scalar_one_or_none()
    contatos = CONTATOS_PADRAO
    if row is not None and row.valor:
        try:
            data = json.loads(row.valor)
            if isinstance(data, list):
                contatos = data
        except ValueError:
            pass  # valor corrompido no banco → padrão versionado, nunca 500
    return _com_link(contatos)


async def definir(session: AsyncSession, contatos: list[dict]) -> None:
    """Substitui a lista inteira (upsert em `configuracoes`, como os módulos)."""
    valor = json.dumps(
        [
            {
                "nome": c.get("nome"),
                "telefone": c.get("telefone"),
                "descricao": c.get("descricao"),
            }
            for c in contatos
        ],
        ensure_ascii=False,
    )
    stmt = (
        pg_insert(Configuracao)
        .values(
            chave=_CHAVE,
            valor=valor,
            secreto=False,
            cifrado=False,
            categoria=_CATEGORIA,
            descricao="Contatos da assessoria (WhatsApp)",
        )
        .on_conflict_do_update(index_elements=["chave"], set_={"valor": valor})
    )
    await session.execute(stmt)
