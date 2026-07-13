"""Normalização de RECEBIDOS: RawRecord → schema canônico `RepasseCanonico`.

Reusa `compute_hash` do normalizer de propostas para detecção de mudança.
No P1 tudo vem de API/CSV oficial → proveniência 'api'.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..connectors.base import RawRecord
from ..schemas.repasse import RepasseCanonico

# campos materiais que entram no hash de mudança
_HASH_FIELDS = (
    "descricao",
    "categoria",
    "orgao_superior",
    "natureza",
    "valor",
    "data_repasse",
    "competencia",
    "documento",
    "emenda",
)


def _to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    s = str(v)
    # formato BR ("1.234,56") → normaliza para "1234.56"
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v)[:19], fmt).date()
        except ValueError:
            continue
    return None


def compute_hash(data: dict[str, Any]) -> str:
    material = {k: data.get(k) for k in _HASH_FIELDS}
    payload = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_repasse(record: RawRecord) -> RepasseCanonico:
    """Mapeia um RawRecord (FPM/Emendas/FNS/FNDE…) para o schema canônico de repasse.

    O connector já entrega o essencial em `record.raw`; campos ausentes ficam None.
    """
    raw = record.raw if isinstance(record.raw, dict) else {}

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "municipio_ibge": record.municipio_ibge or raw.get("municipio_ibge"),
        "municipio_nome": raw.get("municipio_nome"),
        "uf": raw.get("uf"),
        "data_repasse": _to_date(raw.get("data_repasse")),
        "competencia": raw.get("competencia"),
        "descricao": raw.get("descricao"),
        "categoria": raw.get("categoria"),
        "orgao_superior": raw.get("orgao_superior"),
        "natureza": raw.get("natureza") or "repasse",
        "valor": _to_decimal(raw.get("valor")),
        "documento": raw.get("documento"),
        "emenda": bool(raw.get("emenda", False)),
        "detalhe": raw.get("detalhe"),
    }

    proveniencia = {k: "api" for k, v in fields.items() if v not in (None, "", False)}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = compute_hash(fields)

    return RepasseCanonico(**fields)
