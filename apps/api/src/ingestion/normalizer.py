"""Normalização: RawRecord da fonte → schema canônico `PropostaCanonica`.

Também calcula `hash_conteudo` (para detecção de mudança) e `proveniencia`
(auditoria por-campo da origem; no Sprint 1 tudo vem da API => 'api').
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..connectors.base import RawRecord
from ..schemas.proposta import PropostaCanonica
from . import natureza_juridica as nj

# campos "materiais" que entram no hash (mudança neles = mudança relevante)
_HASH_FIELDS = (
    "numero_proposta",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
    "valor_total",
    "contrapartida",
    "situacao",
    "emenda",
    "prazos",
    "pendencias",
    "movimentacao",
    "data_atualizacao_fonte",
)
# `natureza_juridica` fica fora do hash de propósito: é atributo estável do
# proponente (não gera alerta acionável) e incluí-lo faria toda a base existente
# virar "mudança" na primeira sync depois do deploy.

# Campos onde as fontes costumam trazer a natureza jurídica do proponente
# (ponto de calibração ao ligar cada fonte real).
_NATUREZA_TEXTO = (
    "nome_natureza_juridica",
    "natureza_juridica",
    "descricao_natureza_juridica",
    "tipo_beneficiario",
    "tipo_proponente",
    "esfera",
    "esfera_administrativa",
)
_NATUREZA_CODIGO = (
    "codigo_natureza_juridica",
    "id_natureza_juridica",
    "cod_natureza_juridica",
)
_NATUREZA_NOME = ("nome_beneficiario", "nome_proponente", "razao_social", "nome")


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", []):
            return v
    return None


def _to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
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
    """Hash determinístico dos campos materiais (sha256 de JSON sort_keys)."""
    material = {k: data.get(k) for k in _HASH_FIELDS}
    payload = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize(record: RawRecord) -> PropostaCanonica:
    """Mapeia um RawRecord do transferegov_ff para o schema canônico."""
    raw = record.raw
    plano = raw.get("plano_acao", raw) if isinstance(raw, dict) else {}
    programa = raw.get("programa", {}) if isinstance(raw, dict) else {}
    benef = raw.get("beneficiario", {}) if isinstance(raw, dict) else {}

    # Natureza jurídica do proponente: descrição da fonte (quando vem) + a lente
    # canônica de duas vias (entes municipais x outros).
    natureza_textos = [
        _first(benef.get(k), plano.get(k)) for k in _NATUREZA_TEXTO
    ]
    # o nome só vale do bloco do beneficiário (no plano, "nome" é o do objeto)
    natureza_nomes = [benef.get(k) for k in _NATUREZA_NOME]
    natureza_codigo = _first(*(_first(benef.get(k), plano.get(k)) for k in _NATUREZA_CODIGO))

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "numero_proposta": _first(
            plano.get("numero_plano_acao"), plano.get("numero_proposta")
        ),
        "titulo": _first(programa.get("nome_programa"), plano.get("nome")),
        "objeto": _first(programa.get("objeto"), plano.get("objeto")),
        "orgao_superior": _first(
            programa.get("nome_orgao_superior_programa"),
            programa.get("nome_orgao_superior"),
        ),
        "modalidade": _first(programa.get("modalidade"), "Fundo a Fundo"),
        "natureza_juridica": nj.classificar(
            *natureza_textos,
            *natureza_nomes,
            codigo=natureza_codigo,
            fonte=record.source_id,
        ),
        "natureza_juridica_descricao": nj.descrever(*natureza_textos, *natureza_nomes),
        "municipio_ibge": _first(
            record.municipio_ibge, benef.get("codigo_ibge"), plano.get("codigo_ibge")
        ),
        "municipio_nome": _first(benef.get("nome_municipio"), benef.get("municipio")),
        "uf": _first(benef.get("sigla_uf"), benef.get("uf")),
        "valor_total": _to_decimal(
            _first(plano.get("valor_total"), plano.get("valor_repasse_emenda_parlamentar"))
        ),
        "contrapartida": _to_decimal(plano.get("valor_contrapartida")),
        "situacao": _first(plano.get("situacao"), plano.get("situacao_plano_acao")),
        "emenda": _first(plano.get("numero_emenda"), plano.get("emenda")),
        "prazos": None,
        "pendencias": None,
        "movimentacao": None,
        "data_atualizacao_fonte": _to_date(
            _first(plano.get("data_atualizacao"), plano.get("ano_plano_acao"))
        ),
        "url_origem": None,
    }

    # proveniência: no Sprint 1 tudo vem da API
    proveniencia = {k: "api" for k, v in fields.items() if v is not None}
    # a natureza só é "api" quando a fonte informou algo; senão é inferida aqui
    if not (natureza_codigo or any(natureza_textos) or any(natureza_nomes)):
        proveniencia["natureza_juridica"] = "derivado"
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = compute_hash(fields)

    return PropostaCanonica(**fields)
