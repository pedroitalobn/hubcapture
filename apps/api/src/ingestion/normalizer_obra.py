"""Normalização de obras: RawRecord → ObraCanonica.

Reusa o padrão de `normalizer_conformidade`. `compute_hash` sobre os campos que
mudam com o andamento da obra (situação, percentual, valores, prazos) para
disparar re-sync/alerta quando a execução avança.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..connectors.base import RawRecord
from ..schemas.obra import ObraCanonica

_HASH_FIELDS = (
    "nome",
    "objeto",
    "situacao",
    "percentual_execucao",
    "valor_investimento",
    "valor_repassado",
    "data_inicio",
    "data_fim_prevista",
)

# de-para de textos de situação → canônico
_SITUACAO = {
    "planejada": "planejada",
    "proposta": "planejada",
    "em execução": "em_execucao",
    "em execucao": "em_execucao",
    "em obras": "em_execucao",
    "iniciada": "em_execucao",
    "paralisada": "paralisada",
    "inacabada": "paralisada",
    "concluída": "concluida",
    "concluida": "concluida",
    "finalizada": "concluida",
    "cancelada": "cancelada",
}


def _situacao(bruto: Any) -> str | None:
    if bruto in (None, ""):
        return None
    return _SITUACAO.get(str(bruto).strip().lower(), "em_execucao")


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


def normalize_obra(record: RawRecord) -> ObraCanonica:
    raw = record.raw if isinstance(record.raw, dict) else {}
    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "municipio_ibge": record.municipio_ibge or raw.get("municipio_ibge"),
        "municipio_nome": raw.get("municipio_nome"),
        "uf": raw.get("uf"),
        "nome": raw.get("nome") or raw.get("titulo"),
        "objeto": raw.get("objeto") or raw.get("descricao"),
        "programa": raw.get("programa"),
        "eixo": raw.get("eixo"),
        "situacao": _situacao(raw.get("situacao")),
        "percentual_execucao": _to_decimal(raw.get("percentual_execucao")),
        "valor_investimento": _to_decimal(raw.get("valor_investimento")),
        "valor_repassado": _to_decimal(raw.get("valor_repassado")),
        "data_inicio": _to_date(raw.get("data_inicio")),
        "data_fim_prevista": _to_date(raw.get("data_fim_prevista")),
        "latitude": _to_decimal(raw.get("latitude")),
        "longitude": _to_decimal(raw.get("longitude")),
        "endereco": raw.get("endereco"),
        "orgao": raw.get("orgao"),
        "detalhe": raw.get("detalhe"),
    }
    proveniencia = {k: "api" for k, v in fields.items() if v not in (None, "")}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = _hash(fields)
    return ObraCanonica(**fields)
