"""Recorte de território — o filtro de município do painel.

O usuário escolhe N municípios no onboarding; no painel ele decide quais DESSES
quer ver naquele momento. O filtro é, portanto, um SUBCONJUNTO do território —
não "um município ou todos". Por isso todo serviço de leitura dos eixos
(captação, recebidos, conformidade, obras, perfil) aceita `municipio` como um
código IBGE, uma lista de códigos ou nada (= todo o território).

Nada aqui amplia visibilidade: o RLS continua sendo o limite: um IBGE fora do
território do usuário simplesmente não devolve linha.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select

# Um código IBGE, vários, ou nada (todo o território do usuário).
Municipios = str | Sequence[str] | None


def ibges(valor: Municipios) -> list[str]:
    """Normaliza o filtro para uma lista de códigos (vazia = sem recorte)."""
    if valor is None:
        return []
    brutos: Sequence[Any] = [valor] if isinstance(valor, str) else list(valor)
    vistos: dict[str, None] = {}  # dedup preservando a ordem de escolha
    for bruto in brutos:
        codigo = str(bruto).strip()
        if codigo:
            vistos.setdefault(codigo, None)
    return list(vistos)


def condicao(coluna: ColumnElement[Any], valor: Municipios) -> ColumnElement[bool] | None:
    """Condição SQL do recorte, ou None quando não há recorte a aplicar."""
    escolhidos = ibges(valor)
    return coluna.in_(escolhidos) if escolhidos else None


def filtrar(
    stmt: Select[Any], coluna: ColumnElement[Any], valor: Municipios
) -> Select[Any]:
    """Aplica o recorte de município na query (nenhum, um ou vários)."""
    recorte = condicao(coluna, valor)
    return stmt.where(recorte) if recorte is not None else stmt
