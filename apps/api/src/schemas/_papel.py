"""Validação compartilhada do campo `papel` (role do usuário) na ENTRADA.

O CHECK `ck_usuarios_papel` do banco recusa qualquer valor fora de PAPEIS —
inclusive a string vazia que os <select> do painel mandam para "— sem papel —".
Sem normalizar aqui, o INSERT/UPDATE estoura CheckViolation e o admin vê um 500
mudo ("ao criar usuário nada acontece"). Vazio/espaços → None (sem papel);
valor desconhecido → 422 com a lista do que existe.
"""

from __future__ import annotations

from ..models.usuario import PAPEIS


def papel_ou_none(v: object) -> object:
    if not isinstance(v, str):
        return v  # None passa; tipo errado fica para a validação padrão
    valor = v.strip().lower()
    if not valor:
        return None
    if valor not in PAPEIS:
        raise ValueError(f"papel deve ser um de: {', '.join(PAPEIS)}")
    return valor
