"""Normalização de conformidade fiscal: RawRecord → ConformidadeCanonica.

Reusa `compute_hash` (mudança de status/validade dispara re-sync/alerta).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..connectors.base import RawRecord
from ..schemas.conformidade import ConformidadeCanonica

_HASH_FIELDS = ("tipo", "numero", "secao", "descricao", "status", "validade", "orgao", "valor")


def _to_date(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(v)[:10], fmt).date()
        except ValueError:
            continue
    return None


def _to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _hash(data: dict[str, Any]) -> str:
    import hashlib
    import json

    material = {k: data.get(k) for k in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def normalize_conformidade(record: RawRecord) -> ConformidadeCanonica:
    raw = record.raw if isinstance(record.raw, dict) else {}
    fields: dict[str, Any] = {
        "municipio_ibge": record.municipio_ibge or raw.get("municipio_ibge"),
        "municipio_nome": raw.get("municipio_nome"),
        "uf": raw.get("uf"),
        "tipo": raw.get("tipo") or "cauc",
        "numero": str(raw.get("numero") or "1"),
        "secao": raw.get("secao"),
        "descricao": raw.get("descricao"),
        "status": raw.get("status"),
        "validade": _to_date(raw.get("validade")),
        "orgao": raw.get("orgao"),
        "valor": _to_decimal(raw.get("valor")),
        "detalhe": raw.get("detalhe"),
    }
    proveniencia = {k: "api" for k, v in fields.items() if v not in (None, "")}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = _hash(fields)
    return ConformidadeCanonica(**fields)
