"""Normalização: RawRecord da fonte → schema canônico `PropostaCanonica`.

Também calcula `hash_conteudo` (para detecção de mudança) e `proveniencia`
(auditoria por-campo da origem; no Sprint 1 tudo vem da API => 'api').

Classificação temporal: `ano`/`data_criacao_fonte` guardam quando a proposta
NASCEU na fonte. `data_atualizacao_fonte` é a última movimentação e nunca deve
alimentar o ano — senão uma proposta criada em 2022 que se mexeu em 2026
apareceria classificada como 2026.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..connectors.base import RawRecord
from ..schemas.proposta import PropostaCanonica

# campos "materiais" que entram no hash (mudança neles = mudança relevante).
# `ano`/`data_criacao_fonte` ficam de fora: são imutáveis por natureza e entrar
# no hash geraria um falso alerta de mudança em toda proposta já cacheada.
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

# ── Ano de criação: candidatos na origem (ponto de calibração por fonte) ─────
# Datas de criação/cadastro da proposta. NUNCA incluir data de atualização.
_CRIACAO_KEYS = (
    "data_proposta",
    "data_cadastro",
    "data_criacao",
    "data_inclusao",
    "data_envio",
    "dia_proposta",
)
# Campos que já vêm como ano cheio na fonte.
_ANO_KEYS = ("ano_proposta", "ano_plano_acao", "ano_convenio", "ano")
# Nº de proposta do TransfereGov segue 'NNNNNN/AAAA' — o sufixo é o ano de criação.
_ANO_NO_NUMERO = re.compile(r"/\s*((?:19|20)\d{2})")
_ANO_MIN = 1990


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


def _to_ano(v: Any) -> int | None:
    """Extrai um ano plausível de um int/str/date (descarta lixo e datas absurdas)."""
    if v in (None, ""):
        return None
    if isinstance(v, date):
        ano = v.year
    else:
        m = re.search(r"(?:19|20)\d{2}", str(v))
        if m is None:
            return None
        ano = int(m.group())
    # o ano que vem não existe em proposta criada; ano < 1990 é ruído da fonte
    return ano if _ANO_MIN <= ano <= date.today().year + 1 else None


def _ano_do_numero(numero: Any) -> int | None:
    """Ano embutido no número da proposta ('043210/2025' → 2025)."""
    if not numero:
        return None
    m = _ANO_NO_NUMERO.search(str(numero))
    return _to_ano(m.group(1)) if m else None


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

    numero_proposta = _first(
        plano.get("numero_plano_acao"), plano.get("numero_proposta")
    )
    # data em que a proposta foi criada na fonte (não a da última movimentação)
    data_criacao = _to_date(_first(*(plano.get(k) for k in _CRIACAO_KEYS)))
    # ano de criação: data de criação > campo de ano da fonte > sufixo do nº
    ano = _first(
        data_criacao.year if data_criacao else None,
        _to_ano(_first(*(plano.get(k) for k in _ANO_KEYS))),
        _ano_do_numero(numero_proposta),
    )

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "numero_proposta": numero_proposta,
        "ano": ano,
        "titulo": _first(programa.get("nome_programa"), plano.get("nome")),
        "objeto": _first(programa.get("objeto"), plano.get("objeto")),
        "orgao_superior": _first(
            programa.get("nome_orgao_superior_programa"),
            programa.get("nome_orgao_superior"),
        ),
        "modalidade": _first(programa.get("modalidade"), "Fundo a Fundo"),
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
        "data_criacao_fonte": data_criacao,
        # só data de movimentação entra aqui — ano de criação vive em `ano`
        "data_atualizacao_fonte": _to_date(
            _first(
                plano.get("data_atualizacao"),
                plano.get("data_ultima_atualizacao"),
            )
        ),
        "url_origem": None,
    }

    # proveniência: no Sprint 1 tudo vem da API
    proveniencia = {k: "api" for k, v in fields.items() if v is not None}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = compute_hash(fields)

    return PropostaCanonica(**fields)
