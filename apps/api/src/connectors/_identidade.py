"""Identidade do registro coletado — o `id_externo` que o upsert usa como chave.

`propostas`/`repasses`/`obras` têm `unique(fonte, id_externo)`: é por esse par
que a coleta decide se está ATUALIZANDO uma linha ou CRIANDO outra. Um
identificador mal formado, portanto, não é um detalhe cosmético — ele reescreve
o cache.

Dois defeitos apareceram em produção, e é contra eles que este módulo existe:

* **Índice posicional** (`id_externo = i`, `f"painel-{ibge}-{i}"`): a posição
  muda a cada coleta (a fonte reordena, uma linha entra no meio), então a MESMA
  transferência troca de identidade entre rodadas — cria linha nova numa vez,
  sobrescreve a do vizinho na outra. É o "o número de propostas do município
  fica mudando" que o gestor vê.
* **Identificador não escopado no município** (`i` puro, `"None"` quando a
  coluna de id não existe): o par único é GLOBAL, não por município. A proposta
  "1" de Apuiarés e a "1" de outro município são a mesma linha para o banco —
  uma sobrescreve a outra e a linha muda de município, fazendo o filtro de
  território mostrar dado que não é dali.

A regra: se a fonte publica um id, ele manda. Sem id, a identidade é derivada do
CONTEÚDO da linha e escopada no município — estável entre coletas (mesma linha →
mesmo hash) e impossível de colidir com outro território.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _valor(row: dict[str, Any], chave: str) -> str | None:
    """Valor não-vazio de `chave` no dict (aceita qualquer caixa)."""
    for k, v in row.items():
        if str(k).strip().lower() == chave and v not in (None, "", "None"):
            return str(v).strip()
    return None


def hash_conteudo(row: dict[str, Any], ibge: str, *, prefixo: str = "") -> str:
    """Identidade derivada do conteúdo da linha, escopada no município.

    Determinística (`sort_keys`) para a mesma linha render sempre o mesmo id —
    é o que faz a coleta seguinte ATUALIZAR a proposta em vez de duplicá-la.
    """
    payload = json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{prefixo}{ibge}:{digest}"


def id_externo(
    row: dict[str, Any],
    ibge: str,
    *,
    candidatos: tuple[str, ...] = (),
    prefixo: str = "",
) -> str:
    """`id_externo` da linha: o id publicado pela fonte, ou o hash do conteúdo.

    `candidatos` são os nomes de coluna que carregam o id na fonte, em ordem de
    preferência. Nenhum preenchido → cai no hash escopado no município (NUNCA em
    posição na lista, que muda de uma coleta para a outra).
    """
    for chave in candidatos:
        valor = _valor(row, chave)
        if valor:
            return valor
    return hash_conteudo(row, ibge, prefixo=prefixo)
