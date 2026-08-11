"""De-para de campo por PALAVRA da coluna — compartilhado pelos normalizadores.

As rotas do TransfereGov nomeiam a coluna com o sufixo da entidade
(`valor_empenhado_empenho_especial`, `nome_parlamentar_emenda_plano_acao`), e
cada rota irmã escolhe um sufixo diferente para a mesma coisa. Listar todas as
combinações não escala; procurar a chave que CONTÉM os termos, sim.

Casar por substring é armadilha e já custou um bug: "ano" está dentro de
"pl**ano**", e `id_emenda_plano_acao=90871` virava o ano 9087 da emenda. Por
isso a comparação é sobre o CONJUNTO DE PALAVRAS da coluna
(`valor_emenda_plano_acao` → {valor, emenda, plano, acao}).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S")


def palavras(chave: str) -> set[str]:
    """`valor_emenda_plano_acao` → {valor, emenda, plano, acao}."""
    return {p for p in re.split(r"[^a-z0-9]+", chave.lower()) if p}


def por_termos(
    linha: dict, *termos: str, excluir: tuple[str, ...] = ()
) -> Any:
    """Primeiro valor cuja CHAVE tenha todas as palavras (e nenhuma excluída)."""
    for chave, valor in linha.items():
        if not isinstance(chave, str) or valor in (None, "", [], {}):
            continue
        p = palavras(chave)
        if p.issuperset(termos) and not p.intersection(excluir):
            return valor
    return None


def primeiro(*valores: Any) -> Any:
    """Primeiro valor preenchido — a ordem dos candidatos é a precedência."""
    for v in valores:
        if v not in (None, "", [], {}):
            return v
    return None


def texto(v: Any) -> str | None:
    if v in (None, "", [], {}):
        return None
    return " ".join(str(v).split()) or None


def decimal_br(v: Any) -> Decimal | None:
    """Aceita 1234.56 e o pt-BR "1.234.567,89" — sem isso o valor vira lixo."""
    if v in (None, "", []):
        return None
    bruto = str(v).strip().replace("R$", "").strip()
    if "," in bruto and re.search(r",\d{1,2}$", bruto):
        bruto = bruto.replace(".", "").replace(",", ".")
    bruto = bruto.replace(" ", "")
    try:
        return Decimal(bruto)
    except (InvalidOperation, ValueError):
        return None


def ano_de(v: Any) -> int | None:
    achado = re.search(r"\d{4}", str(v or ""))
    return int(achado.group()) if achado else None


def data_de(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    bruto = str(v).strip()
    for fmt in _FORMATOS_DATA:
        try:
            return datetime.strptime(bruto[: len(fmt) + 6], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(bruto[:10])
    except ValueError:
        return None


def so_digitos(v: Any) -> str:
    """Chave de comparação entre formatos: "14275/2026" e "142752026" casam."""
    return re.sub(r"\D", "", str(v or ""))
