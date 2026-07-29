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
    "execucao",
)


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


# colunas de execução financeira do painel TransfereGov (Visão Geral) — o
# "quanto foi disponibilizado (empenhado) e ainda não utilizado" que o gestor
# quer ver. Aceita tanto snake_case quanto os cabeçalhos do relatório.
_EXEC_KEYS = {
    "valor_global": ("valor_global", "valor global", "vl_global"),
    "valor_empenhado": ("valor_empenhado", "valor empenhado", "vl_empenhado"),
    "valor_liberado": ("valor_liberado", "valor liberado", "vl_desembolsado", "vl_liberado"),
    "valor_pago": ("valor_pago", "valor pago", "vl_pago"),
    "saldo_conta": ("saldo_conta", "saldo em conta", "vl_saldo"),
    "ano": ("ano",),
    "qtd_transferencias": ("qtd_transferencias", "qtd. transferencias"),
    "ente_recebedor": ("ente_recebedor", "ente recebedor"),
    "natureza_juridica": ("natureza_juridica", "natureza juridica"),
    "data_assinatura": ("data_assinatura", "data assinatura"),
    "data_inicio_vigencia": ("data_inicio_vigencia", "data inicio vigencia"),
    "data_fim_vigencia": ("data_fim_vigencia", "data fim vigencia"),
    "tipo_transferencia": ("tipo_transferencia", "tipo transferencia"),
}


def _montar_execucao(plano: dict) -> dict | None:
    """Extrai o bloco de execução financeira quando a fonte o fornece."""
    normalizado = {
        k.strip().lower().replace("ê", "e").replace("ã", "a").replace("ç", "c"): v
        for k, v in plano.items()
        if isinstance(k, str)
    }
    execucao: dict = {}
    for destino, candidatos in _EXEC_KEYS.items():
        for c in candidatos:
            if c in normalizado and normalizado[c] not in (None, ""):
                v = normalizado[c]
                execucao[destino] = str(v) if destino.startswith(("valor", "saldo")) else v
                break
    return execucao or None


def normalize(record: RawRecord) -> PropostaCanonica:
    """Mapeia um RawRecord (plano de ação, convênio ou painel) p/ o schema canônico."""
    raw = record.raw
    plano = raw.get("plano_acao", raw) if isinstance(raw, dict) else {}
    programa = raw.get("programa", {}) if isinstance(raw, dict) else {}
    benef = raw.get("beneficiario", {}) if isinstance(raw, dict) else {}

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "numero_proposta": _first(
            plano.get("numero_plano_acao"),
            plano.get("numero_proposta"),
            plano.get("numero_convenio"),  # voluntárias (convênio)
            plano.get("codigo_plano_acao"),  # fundo a fundo
            plano.get("numero"),  # painel SERPRO
        ),
        "titulo": _first(
            programa.get("nome_programa"), plano.get("nome"), plano.get("programa")
        ),
        "objeto": _first(
            programa.get("objeto"),
            plano.get("objeto"),
            plano.get("objeto_convenio"),
            plano.get("objeto_proposta"),
            plano.get("objetivos_plano_acao"),  # fundo a fundo
            plano.get("diagnostico_plano_acao"),  # fundo a fundo (fallback)
        ),
        "orgao_superior": _first(
            programa.get("nome_orgao_superior_programa"),
            programa.get("nome_orgao_superior"),
            plano.get("nome_orgao_superior"),
            plano.get("nome_orgao_repassador_plano_acao"),  # fundo a fundo
            plano.get("orgao"),
        ),
        "modalidade": _first(
            raw.get("modalidade") if isinstance(raw, dict) else None,
            programa.get("modalidade"),
            plano.get("modalidade"),
            "Fundo a Fundo",
        ),
        "municipio_ibge": _first(
            record.municipio_ibge, benef.get("codigo_ibge"), plano.get("codigo_ibge")
        ),
        "municipio_nome": _first(
            benef.get("nome_municipio"),
            benef.get("municipio"),
            plano.get("nome_municipio_ente_recebedor_plano_acao"),  # fundo a fundo
            plano.get("nome_municipio_ente_repassador_plano_acao"),
        ),
        "uf": _first(
            benef.get("sigla_uf"),
            benef.get("uf"),
            plano.get("uf"),
            plano.get("uf_ente_recebedor_plano_acao"),  # fundo a fundo
            plano.get("uf_ente_repassador_plano_acao"),
        ),
        "valor_total": _to_decimal(
            _first(
                plano.get("valor_total"),
                plano.get("valor_repasse_emenda_parlamentar"),
                plano.get("valor_global"),  # voluntárias (convênio)
                plano.get("valor_total_repasse_plano_acao"),  # fundo a fundo
                plano.get("valor_total_plano_acao"),
                plano.get("valor"),
            )
        ),
        "contrapartida": _to_decimal(
            _first(plano.get("valor_contrapartida"), plano.get("vl_contrapartida"))
        ),
        "situacao": _first(
            plano.get("situacao"),
            plano.get("situacao_plano_acao"),
            plano.get("situacao_convenio"),
        ),
        "emenda": _first(plano.get("numero_emenda"), plano.get("emenda")),
        "prazos": None,
        "pendencias": None,
        "movimentacao": None,
        "data_atualizacao_fonte": _to_date(
            _first(
                plano.get("data_atualizacao"),
                plano.get("data"),
                plano.get("ano_plano_acao"),
            )
        ),
        "url_origem": _first(plano.get("link"), plano.get("url"), plano.get("url_origem")),
        "execucao": _montar_execucao(plano) if isinstance(plano, dict) else None,
    }

    # fim de vigência vira prazo estruturado (alimenta /proposals/deadlines)
    execucao = fields.get("execucao") or {}
    fim_vigencia = _to_date(execucao.get("data_fim_vigencia"))
    if fim_vigencia:
        fields["prazos"] = [{"tipo": "fim de vigência", "data_limite": fim_vigencia.isoformat()}]

    # proveniência por-campo: registros vindos de scraper marcam 'scrape'
    origem = "scrape" if record.endpoint in ("scrape", "firecrawl", "crawl4ai") else "api"
    proveniencia = {k: origem for k, v in fields.items() if v is not None}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = compute_hash(fields)

    return PropostaCanonica(**fields)
