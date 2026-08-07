"""Normalização de parecer: linha bruta (API ou scraping) → schema canônico.

Mesma disciplina de `normalizer_obra`: hash LOCAL sobre os campos materiais do
parecer. `compute_hash` de `normalizer.py` filtra pelos campos da PROPOSTA, então
reusá-lo aqui daria o mesmo hash para todo parecer (nenhuma mudança seria
detectada). Reusa daquele módulo só o `_ci` (alias de caixa — a fonte manda
cabeçalho em CAIXA ALTA, ver §35).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from ..schemas.parecer import ParecerCanonico
from .normalizer import _ci

_HASH_FIELDS = (
    "numero_plano_trabalho",
    "data_parecer",
    "esfera",
    "responsavel",
    "papel",
    "cargo",
    "situacao",
    "texto",
)


def _hash(data: dict[str, Any]) -> str:
    material = {k: data.get(k) for k in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", []):
            return v
    return None


def _to_date(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v).strip()[:19], fmt).date()
        except ValueError:
            continue
    return None


def _texto(v: Any) -> str | None:
    if v in (None, ""):
        return None
    return " ".join(str(v).split()) or None


def _esfera(v: Any) -> str | None:
    """'CONCEDENTE' / 'CONVENENTE' → slug. Texto livre passa normalizado."""
    t = (_texto(v) or "").lower()
    if "concedente" in t:
        return "concedente"
    if "convenente" in t or "proponente" in t:
        return "convenente"
    return _texto(v)


def normalize_parecer(
    bruto: dict,
    *,
    numero_plano_trabalho: str,
    fonte: str,
    numero_proposta: str | None = None,
    municipio_ibge: str | None = None,
) -> ParecerCanonico:
    r = _ci(bruto)

    data_parecer = _to_date(
        _first(r.get("data"), r.get("data_parecer"), r.get("dt_parecer"), r.get("data_analise"))
    )
    responsavel = _texto(
        _first(r.get("responsavel"), r.get("nome"), r.get("usuario"), r.get("nome_responsavel"))
    )
    papel = _texto(_first(r.get("papel"), r.get("perfil"), r.get("funcao"), r.get("tipo_perfil")))
    cargo = _texto(_first(r.get("cargo"), r.get("funcao_cargo"), r.get("descricao_cargo")))

    fields: dict[str, Any] = {
        "fonte": fonte,
        "numero_plano_trabalho": str(numero_plano_trabalho).strip(),
        "numero_proposta": numero_proposta,
        "municipio_ibge": municipio_ibge,
        "data_parecer": data_parecer,
        "esfera": _esfera(_first(r.get("esfera"), r.get("origem"), r.get("tipo"))),
        "responsavel": responsavel,
        "papel": papel,
        "cargo": cargo,
        "situacao": _texto(_first(r.get("situacao"), r.get("resultado"), r.get("status"))),
        "texto": _texto(_first(r.get("texto"), r.get("parecer"), r.get("descricao"))),
        "url_parecer": _first(
            r.get("url_parecer"), r.get("link"), r.get("url"), r.get("href")
        ),
        "detalhe": bruto,
    }

    # id_externo: a fonte raramente dá um id para a linha de tramitação, então a
    # identidade é a combinação que a torna única (plano + data + quem assinou).
    # Sem isso, cada sync duplicaria o mesmo parecer.
    fields["id_externo"] = _first(
        r.get("id_externo"),
        r.get("id"),
        r.get("id_parecer"),
        "|".join(
            str(x)
            for x in (
                fields["numero_plano_trabalho"],
                data_parecer.isoformat() if data_parecer else "",
                (responsavel or "").lower(),
                (papel or "").lower(),
            )
        ),
    )

    origem = "scrape" if bruto.get("_scraper") else "api"
    fields["proveniencia"] = {k: origem for k, v in fields.items() if v is not None}
    fields["proveniencia"]["_fonte"] = fonte
    fields["hash_conteudo"] = _hash(fields)

    return ParecerCanonico(**fields)
