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
    "numero_plano_trabalho",
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
    "data_proposta",
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
    s = str(v).strip()
    if "," in s:  # formato BR ("1.234,56") → "1234.56"
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _somar(dados: dict[str, Any], campos: tuple[str, ...]) -> Decimal | None:
    parcelas = [_to_decimal(dados.get(c)) for c in campos]
    presentes = [p for p in parcelas if p is not None]
    return sum(presentes, Decimal(0)) if presentes else None


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


def _data_de_componentes(plano: dict) -> date | None:
    """Data remontada das colunas decompostas do SIconv: DIA_PROP/MES_PROP/ANO_PROP.

    É a data OFICIAL de criação da proposta na fonte — quando os três componentes
    existem, vencem qualquer candidato de coluna única (que ora é vigência, ora
    é cadastro de outra coisa e vinha marcando a proposta com data errada).
    """
    try:
        dia = int(str(plano.get("dia_prop")).strip())
        mes = int(str(plano.get("mes_prop")).strip())
        ano = int(str(plano.get("ano_prop")).strip())
        return date(ano, mes, dia)
    except (TypeError, ValueError):
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
    # VL_GLOBAL_PROP é a variável do SIconv para o valor global da PROPOSTA
    # (VL_GLOBAL_CONV é a do convênio já celebrado). Sem estes aliases o campo
    # só chegava quando o connector já tinha feito o de-para por palavra-chave.
    "valor_global": (
        "valor_global",
        "valor global",
        "vl_global",
        "vl_global_prop",
        "vl_global_conv",
    ),
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


def _ci(d: Any) -> dict:
    """Acesso indiferente à caixa: os candidatos abaixo são todos snake_case,
    mas as fontes não. O CSV do SIconv/detru manda cabeçalho em CAIXA ALTA
    (`NR_PROPOSTA`, `DIA_PROPOSTA`) e nenhum candidato casava — o número da
    proposta simplesmente não chegava à tela. Só ADICIONA o alias minúsculo:
    chave já existente nunca é sobrescrita, então nada muda para quem já casava.
    """
    if not isinstance(d, dict):
        return {}
    saida = dict(d)
    for k, v in d.items():
        if isinstance(k, str):
            saida.setdefault(k.strip().lower(), v)
    return saida


def normalize(record: RawRecord) -> PropostaCanonica:
    """Mapeia um RawRecord (plano de ação, convênio ou painel) p/ o schema canônico."""
    raw = record.raw
    plano = _ci(raw.get("plano_acao", raw) if isinstance(raw, dict) else {})
    programa = _ci(raw.get("programa", {}) if isinstance(raw, dict) else {})
    benef = _ci(raw.get("beneficiario", {}) if isinstance(raw, dict) else {})

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "numero_proposta": _first(
            # NR_PROPOSTA (SIconv/detru, "14275/2026") é a referência oficial —
            # é o nº que o gestor digita no portal, então vence os demais
            plano.get("nr_proposta"),
            plano.get("numero_plano_acao"),
            plano.get("numero_proposta"),
            plano.get("numero_convenio"),
            plano.get("nr_convenio"),  # voluntárias (convênio)
            plano.get("codigo_plano_acao"),  # fundo a fundo
            plano.get("numero"),  # painel SERPRO
        ),
        # nº do plano de trabalho — é por ele que a fonte emite os PARECERES
        "numero_plano_trabalho": _first(
            plano.get("numero_plano_trabalho"),
            plano.get("nr_plano_trabalho"),
            plano.get("id_plano_trabalho"),
            plano.get("cd_plano_trabalho"),
            plano.get("numero_plano_acao"),
            plano.get("id_plano_acao"),
        ),
        "titulo": _first(
            programa.get("nome_programa"),
            plano.get("nome"),
            plano.get("programa"),
            # especiais: emenda parlamentar (não há nome de programa)
            (
                f"Transferência especial — {plano['nome_parlamentar_emenda_plano_acao']}"
                if plano.get("nome_parlamentar_emenda_plano_acao")
                else None
            ),
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
            plano.get("desc_orgao"),  # SIconv/detru ("MINISTÉRIO DA ...")
            plano.get("desc_orgao_superior"),
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
            plano.get("nome_beneficiario_plano_acao"),  # especiais
        ),
        "uf": _first(
            benef.get("sigla_uf"),
            benef.get("uf"),
            plano.get("uf"),
            plano.get("uf_ente_recebedor_plano_acao"),  # fundo a fundo
            plano.get("uf_ente_repassador_plano_acao"),
            plano.get("uf_beneficiario_plano_acao"),  # especiais
        ),
        "valor_total": _first(
            _to_decimal(
                _first(
                    plano.get("valor_total"),
                    plano.get("valor_repasse_emenda_parlamentar"),
                    plano.get("valor_global"),  # voluntárias (convênio)
                    plano.get("valor_total_repasse_plano_acao"),  # fundo a fundo
                    plano.get("valor_total_plano_acao"),
                )
            ),
            # especiais: sem campo de total, o valor é custeio + investimento —
            # pegar só um dos dois subestima a proposta
            _somar(
                plano,
                ("valor_investimento_plano_acao", "valor_custeio_plano_acao"),
            ),
            _to_decimal(plano.get("valor")),
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
        # Quando a proposta foi CRIADA na fonte. O gestor cita a proposta por
        # número e data ("14275/2026, de 26/03") — é dado de cabeçalho, não o
        # mesmo que `data_atualizacao_fonte` (quando a fonte mexeu no registro).
        "data_proposta": _first(
            _data_de_componentes(plano),  # SIconv: DIA_PROP/MES_PROP/ANO_PROP
            _to_date(
                _first(
                    plano.get("dia_proposta"),  # SIconv/detru (data em coluna única)
                    plano.get("data_proposta"),
                    plano.get("data_cadastro"),
                    plano.get("data_criacao"),
                    plano.get("dia_cadastro"),
                    plano.get("data_inicio_vigencia"),  # sem data própria: a vigência abre
                )
            ),
        ),
        "data_atualizacao_fonte": _to_date(
            _first(
                plano.get("data_atualizacao"),
                plano.get("data"),
                plano.get("ano_plano_acao"),
            )
        ),
        "url_origem": _first(plano.get("link"), plano.get("url"), plano.get("url_origem")),
        "execucao": _montar_execucao(plano) if isinstance(plano, dict) else None,
        # registro-fonte COMPLETO (todos os campos) p/ o detalhe exibir "tudo"
        "dados_fonte": raw if isinstance(raw, dict) else None,
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
