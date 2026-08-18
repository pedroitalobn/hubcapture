"""Diretório institucional — gabinetes, chefias, assessorias e SEIs.

Ponto 19 do feedback do cliente: na agenda de contatos "será enviado relação de
Gabinete dos ministros, Chefia de Gabinete, Assessorias Parlamentares e os SEIs
dos protocolos". Isso NÃO é a agenda pessoal do gestor (`contatos`, por-tenant
com RLS `FOR ALL`): é uma lista curada, igual para todos os clientes, que a
administração mantém e o usuário só consulta.

Por isso segue a mecânica do `services/assessoria`: uma chave em
`configuracoes` (nível-plataforma), sem migration, editável em runtime pelo
painel admin. Adicionar contato é mudar dado, não código.

O **SEI do protocolo** é campo de primeira classe aqui, e não uma nota solta: é
por ele que o gestor cobra o andamento do processo no órgão, e ele precisa
poder copiar o número sem garimpar no meio de um texto.
"""

from __future__ import annotations

import json
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.configuracao import Configuracao

_CHAVE = "contatos_institucionais"
_CATEGORIA = "contatos"

# As quatro naturezas que o cliente pediu. É o eixo pelo qual o gestor procura
# ("preciso falar com a chefia de gabinete do MS"), então vira filtro na tela.
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("gabinete_ministro", "Gabinete de ministro"),
    ("chefia_gabinete", "Chefia de gabinete"),
    ("assessoria_parlamentar", "Assessoria parlamentar"),
    ("sei_protocolo", "SEI / protocolo"),
    ("outros", "Outros"),
)
_ROTULOS = dict(CATEGORIAS)


def categoria_valida(chave: str | None) -> str:
    """Categoria conhecida, ou `outros` — lista curada não pode virar 500."""
    return chave if chave in _ROTULOS else "outros"


def _sem_acento(texto: str) -> str:
    sem = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower()


def whatsapp_url(telefone: str | None) -> str | None:
    """Link wa.me quando há telefone — mesma regra do `services/assessoria`.

    O critério é o COMPRIMENTO, não o prefixo: um número local do DDD 55 (RS)
    também começa com "55" e um startswith prefixaria errado.
    """
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return None
    if len(digitos) <= 11:  # DDD + número, sem DDI
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def _normalizar(c: dict) -> dict | None:
    """Uma entrada da lista, saneada. `None` = entrada sem nada que identifique."""
    nome = (c.get("nome") or "").strip()
    orgao = (c.get("orgao") or "").strip()
    if not nome and not orgao:
        return None
    return {
        "nome": nome or orgao,
        "orgao": orgao or None,
        "cargo": (c.get("cargo") or "").strip() or None,
        "categoria": categoria_valida(c.get("categoria")),
        "email": (c.get("email") or "").strip() or None,
        "telefone": (c.get("telefone") or "").strip() or None,
        # número do processo no SEI + link direto, quando o órgão publica
        "sei": (c.get("sei") or "").strip() or None,
        "sei_url": (c.get("sei_url") or "").strip() or None,
        "observacao": (c.get("observacao") or "").strip() or None,
    }


def _para_leitura(c: dict) -> dict:
    return {
        **c,
        "categoria_rotulo": _ROTULOS.get(c["categoria"], "Outros"),
        "whatsapp_url": whatsapp_url(c.get("telefone")),
    }


def _do_banco(row: Configuracao | None) -> list[dict]:
    if row is None or not row.valor:
        return []
    try:
        data = json.loads(row.valor)
    except ValueError:
        return []  # valor corrompido → lista vazia, nunca 500
    if not isinstance(data, list):
        return []
    return [n for n in (_normalizar(c) for c in data if isinstance(c, dict)) if n]


async def listar(
    session: AsyncSession, *, q: str | None = None, categoria: str | None = None
) -> list[dict]:
    """Diretório efetivo, filtrável por busca livre e categoria."""
    row = (
        await session.execute(select(Configuracao).where(Configuracao.chave == _CHAVE))
    ).scalar_one_or_none()
    itens = _do_banco(row)

    if categoria:
        itens = [c for c in itens if c["categoria"] == categoria]
    if q and q.strip():
        alvo = _sem_acento(q.strip())
        # a busca alcança o SEI de propósito: o gestor costuma ter o número do
        # processo em mãos e querer saber com quem falar sobre ele
        itens = [
            c
            for c in itens
            if any(
                alvo in _sem_acento(str(c.get(campo) or ""))
                for campo in ("nome", "orgao", "cargo", "email", "sei", "observacao")
            )
        ]

    itens.sort(key=lambda c: (_sem_acento(c.get("orgao") or "~"), _sem_acento(c["nome"])))
    return [_para_leitura(c) for c in itens]


async def definir(session: AsyncSession, contatos: list[dict]) -> None:
    """Substitui o diretório inteiro (upsert em `configuracoes`)."""
    saneados = [n for n in (_normalizar(c) for c in contatos) if n]
    valor = json.dumps(saneados, ensure_ascii=False)
    stmt = (
        pg_insert(Configuracao)
        .values(
            chave=_CHAVE,
            valor=valor,
            secreto=False,
            cifrado=False,
            categoria=_CATEGORIA,
            descricao="Diretório institucional (gabinetes, assessorias, SEIs)",
        )
        .on_conflict_do_update(index_elements=["chave"], set_={"valor": valor})
    )
    await session.execute(stmt)
