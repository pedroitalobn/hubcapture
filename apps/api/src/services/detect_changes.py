"""Detecção de mudança — funções puras (comparação de hash + montagem de payload).

O `hash_conteudo` é calculado na normalização; comparar o antigo ao novo indica
se status/prazo/pendência mudaram. Usado pelo pipeline de sync e pelos alertas.
"""

from __future__ import annotations

from typing import Any


def hash_mudou(antigo: str | None, novo: str | None) -> bool:
    """True somente quando havia um valor anterior e ele mudou."""
    return antigo is not None and novo is not None and antigo != novo


def montar_payload(antes: dict[str, Any], depois: dict[str, Any]) -> dict[str, Any]:
    """Payload antes/depois só com os campos que mudaram (auditoria do alerta)."""
    campos = set(antes) | set(depois)
    diff = {
        k: {"antes": antes.get(k), "depois": depois.get(k)}
        for k in campos
        if antes.get(k) != depois.get(k)
    }
    return {"mudou": diff}


def classificar(diff: dict[str, Any]) -> str:
    """Tipo do alerta a partir dos campos que mudaram."""
    mudou = diff.get("mudou", {})
    if "situacao" in mudou:
        return "status"
    if "prazos" in mudou:
        return "prazo"
    if "pendencias" in mudou:
        return "pendencia"
    return "status"
