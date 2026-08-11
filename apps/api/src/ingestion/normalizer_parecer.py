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
from decimal import Decimal, InvalidOperation
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
    "situacao_analise",
    "situacao_planejamento",
    "valor_reprovado",
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


def _to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
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
        _first(
            r.get("data_analise_pt"),  # API: AAAA-MM-DD
            r.get("data"),
            r.get("data_parecer"),
            r.get("dt_parecer"),
            r.get("data_analise"),
        )
    )
    responsavel = _texto(
        _first(r.get("responsavel"), r.get("nome"), r.get("usuario"), r.get("nome_responsavel"))
    )
    papel = _texto(_first(r.get("papel"), r.get("perfil"), r.get("funcao"), r.get("tipo_perfil")))
    cargo = _texto(_first(r.get("cargo"), r.get("funcao_cargo"), r.get("descricao_cargo")))

    fields: dict[str, Any] = {
        "fonte": fonte,
        "numero_plano_trabalho": str(
            _first(r.get("id_plano_trabalho"), numero_plano_trabalho)
        ).strip(),
        "numero_proposta": numero_proposta,
        "municipio_ibge": municipio_ibge,
        "data_parecer": data_parecer,
        "esfera": _esfera(_first(r.get("esfera"), r.get("origem"), r.get("tipo"))),
        "responsavel": responsavel,
        "papel": papel,
        "cargo": cargo,
        # veredito da análise — o campo que responde "em que pé está"
        "situacao": _texto(
            _first(
                r.get("situacao_parecer_analise_pt"),
                r.get("situacao"),
                r.get("resultado"),
                r.get("status"),
            )
        ),
        "situacao_analise": _texto(_first(r.get("situacao_analise_pt"), r.get("situacao_analise"))),
        "situacao_planejamento": _texto(
            _first(r.get("situacao_planejamento_pt"), r.get("situacao_planejamento"))
        ),
        "orgao_analise": _texto(
            _first(r.get("nome_orgao_analise_pt"), r.get("orgao_analise"), r.get("orgao"))
        ),
        "codigo_siorg_orgao": _texto(
            _first(r.get("codigo_siorg_orgao_analise_pt"), r.get("codigo_siorg_orgao"))
        ),
        "valor_reprovado": _to_decimal(
            _first(r.get("valor_reprovado_pt"), r.get("valor_reprovado"))
        ),
        "texto": _texto(
            _first(
                r.get("texto_parecer_analise_pt"),
                r.get("texto"),
                r.get("parecer"),
                r.get("descricao"),
            )
        ),
        "url_parecer": _first(r.get("url_parecer"), r.get("link"), r.get("url"), r.get("href")),
        "detalhe": bruto,
    }

    # Identidade: a API dá id próprio da análise (`id_plano_trabalho_analise_pt`)
    # e é ele que manda. A chave sintética (plano|data|responsável|papel) só entra
    # quando a linha vem do SCRAPING, que não tem id — sem ela, cada coleta
    # duplicaria o mesmo parecer.
    # `str(...)`: a API devolve os ids como INTEIRO e o schema é string
    fields["id_externo"] = str(
        _first(
            r.get("id_plano_trabalho_analise_pt"),
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
    )

    origem = "scrape" if bruto.get("_scraper") else "api"
    fields["proveniencia"] = {k: origem for k, v in fields.items() if v is not None}
    fields["proveniencia"]["_fonte"] = fonte
    fields["hash_conteudo"] = _hash(fields)

    return ParecerCanonico(**fields)
