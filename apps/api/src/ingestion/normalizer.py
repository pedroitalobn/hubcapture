"""Normalização: RawRecord da fonte → schema canônico `PropostaCanonica`.

Também calcula `hash_conteudo` (para detecção de mudança) e `proveniencia`
(auditoria por-campo da origem).

Cada fonte nomeia as colunas de um jeito — a API Fundo a Fundo sufixa tudo com a
entidade (`nome_programa`, `ano_plano_acao`), as voluntárias falam em convênio, o
CSV das discricionárias vem em maiúsculas (`NR_CONVENIO`) — e cada connector
entrega o registro num bloco diferente de `raw` (`plano_acao`, `csv`, `scrape`).
Em vez de um mapeamento por fonte, o normalizador ACHATA os blocos num único
dicionário de chaves minúsculas e resolve cada campo canônico por uma lista de
candidatos. Acrescentar uma variante de nome é acrescentar uma string: este é o
ponto de calibração contra a API viva.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
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
    "descricao",
    "orgao_superior",
    "modalidade",
    "ano",
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

# blocos de `raw` que carregam campos de proposta, do mais específico para o
# mais genérico — o primeiro a definir uma chave vence (o plano de ação é o
# registro concreto; o programa é o guarda-chuva que o contém).
_BLOCOS = ("plano_acao", "csv", "convenio", "proposta", "api", "beneficiario", "programa", "scrape")

# Candidatos por campo canônico. Ponto de calibração contra as APIs vivas.
_CANDIDATOS: dict[str, tuple[str, ...]] = {
    "numero_proposta": (
        "numero_plano_acao",
        "codigo_plano_acao",
        "numero_proposta",
        "nr_proposta",
        "id_proposta",
        "numero_convenio",
        "nr_convenio",
        "numero",
    ),
    "titulo": (
        "nome_programa",
        "nome_plano_acao",
        "nome_acao",
        "titulo",
        "programa",
        "nm_programa",
        "nome",
    ),
    "objeto": (
        "objeto",
        "objeto_proposta",
        "objeto_convenio",
        "objeto_plano_acao",
        "objeto_programa",
        "ds_objeto",
        "descricao_plano_acao",
    ),
    "descricao": (
        "descricao_programa",
        "descricao",
        "descricao_proposta",
        "detalhamento",
        "justificativa",
        "ds_programa",
    ),
    "orgao_superior": (
        "nome_orgao_superior_programa",
        "nome_orgao_superior",
        "orgao_superior",
        "desc_orgao_superior",
        "nome_orgao_concedente",
        "orgao_concedente",
        "nm_orgao_superior",
        "orgao",
    ),
    "modalidade": (
        "modalidade",
        "modalidade_programa",
        "modalidade_proposta",
        "nome_modalidade",
    ),
    "municipio_ibge": ("codigo_ibge", "cod_ibge", "municipio_ibge", "id_municipio_ibge"),
    "municipio_nome": (
        "nome_municipio",
        "municipio",
        "municipio_beneficiario",
        "nome_beneficiario",
        "razao_social",
        "no_municipio",
    ),
    "uf": ("sigla_uf", "uf", "uf_beneficiario", "sg_uf", "sigla_uf_beneficiario"),
    "situacao": (
        "situacao_plano_acao",
        "situacao",
        "situacao_convenio",
        "situacao_proposta",
        "situacao_programa",
        "status",
        "ds_situacao",
    ),
    "emenda": ("numero_emenda", "emenda", "nr_emenda", "codigo_emenda"),
    "url_origem": ("url_origem", "url", "link", "source_url"),
}

_VALOR_TOTAL = (
    "valor_total",
    "valor_total_plano_acao",
    "valor_repasse_emenda_parlamentar",
    "valor_proposta",
    "valor_global",
    "vl_global",
    "valor_repasse",
    "valor",
)
# sem total explícito, o Fundo a Fundo entrega o valor nas duas parcelas
_VALOR_PARCELAS = (
    "valor_custeio_plano_acao",
    "valor_investimento_plano_acao",
    "valor_custeio",
    "valor_investimento",
)
_CONTRAPARTIDA = (
    "valor_contrapartida",
    "valor_contrapartida_plano_acao",
    "contrapartida",
    "vl_contrapartida",
)
_ANO = ("ano_plano_acao", "ano_programa", "ano_proposta", "ano", "exercicio")
_DATA_ATUALIZACAO = (
    "data_atualizacao",
    "data_ultima_atualizacao",
    "dt_atualizacao",
    "data_situacao",
    "data_envio_plano_acao",
    "data_assinatura",
    "data",
)

# modalidade implícita quando a fonte não devolve o campo
_MODALIDADE_PADRAO = {
    "transferegov_ff": "Fundo a Fundo",
    "transferegov_esp": "Transferência Especial",
    "transferegov_disc": "Discricionária",
    "transferegov_voluntarias": "Voluntária",
}

_TITULO_MAX = 120

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


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def _flatten(raw: Any) -> dict[str, Any]:
    """Achata os blocos de `raw` num único dict de chaves minúsculas sem acento."""
    achatado: dict[str, Any] = {}

    def absorver(bloco: Any) -> None:
        if not isinstance(bloco, dict):
            return
        for k, v in bloco.items():
            if isinstance(v, (dict, list)):
                continue
            chave = _sem_acento(str(k).strip().lower())
            if achatado.get(chave) in (None, ""):
                achatado[chave] = v

    if not isinstance(raw, dict):
        return achatado
    for nome in _BLOCOS:
        absorver(raw.get(nome))
    absorver(raw)  # escalares no topo (ex.: `modalidade` do esp/disc)
    return achatado


def _pick(dados: dict[str, Any], candidatos: tuple[str, ...]) -> Any:
    for c in candidatos:
        v = dados.get(c)
        if v not in (None, "", []):
            return v
    return None


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", []):
            return v
    return None


def _texto(v: Any) -> str | None:
    if v in (None, ""):
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


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


def _to_ano(v: Any) -> int | None:
    """Extrai o exercício de um ano solto ou de um número tipo '043210/2025'."""
    if v in (None, ""):
        return None
    m = re.search(r"(?:19|20)\d{2}", str(v))
    if not m:
        return None
    ano = int(m.group(0))
    return ano if 1990 <= ano <= date.today().year + 10 else None


def _titulo(
    dados: dict[str, Any],
    record: RawRecord,
    *,
    numero: str | None,
    objeto: str | None,
    modalidade: str | None,
) -> str:
    """Título nunca vem vazio: desce do nome da fonte para o objeto e daí para o id.

    Sem esta escada a linha aparecia como '—' no painel; qualquer um dos degraus
    identifica a proposta melhor do que isso.
    """
    nome = _texto(_pick(dados, _CANDIDATOS["titulo"]))
    if nome:
        return nome
    if objeto:
        return objeto if len(objeto) <= _TITULO_MAX else f"{objeto[: _TITULO_MAX - 1]}…"
    if numero:
        return f"{modalidade or 'Proposta'} {numero}"
    return f"{modalidade or record.source_id} {record.id_externo}"


def compute_hash(data: dict[str, Any]) -> str:
    """Hash determinístico dos campos materiais (sha256 de JSON sort_keys)."""
    material = {k: data.get(k) for k in _HASH_FIELDS}
    payload = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _montar_execucao(dados: dict[str, Any]) -> dict | None:
    """Extrai o bloco de execução financeira quando a fonte o fornece.

    Recebe o dict já achatado/normalizado por `_flatten`.
    """
    execucao: dict = {}
    for destino, candidatos in _EXEC_KEYS.items():
        for c in candidatos:
            if dados.get(c) not in (None, ""):
                v = dados[c]
                execucao[destino] = str(v) if destino.startswith(("valor", "saldo")) else v
                break
    return execucao or None


def normalize(record: RawRecord) -> PropostaCanonica:
    """Mapeia um RawRecord (plano de ação, convênio, CSV ou painel) p/ o canônico."""
    dados = _flatten(record.raw)

    numero = _texto(_pick(dados, _CANDIDATOS["numero_proposta"]))
    objeto = _texto(_pick(dados, _CANDIDATOS["objeto"]))
    descricao = _texto(_pick(dados, _CANDIDATOS["descricao"]))
    # objeto e descrição se cobrem: a fonte que traz só um dos dois preenche os
    # dois, para o painel nunca mostrar as duas linhas vazias.
    objeto, descricao = objeto or descricao, descricao or objeto

    modalidade = _texto(_pick(dados, _CANDIDATOS["modalidade"])) or _MODALIDADE_PADRAO.get(
        record.source_id
    )
    valor_total = _to_decimal(_pick(dados, _VALOR_TOTAL)) or _somar(dados, _VALOR_PARCELAS)
    execucao = _montar_execucao(dados)
    data_fonte = _to_date(_pick(dados, _DATA_ATUALIZACAO))
    ano = _first(
        _to_ano(_pick(dados, _ANO)),
        _to_ano(numero),
        _to_ano((execucao or {}).get("ano")),
        data_fonte.year if data_fonte else None,
    )

    fields: dict[str, Any] = {
        "fonte": record.source_id,
        "id_externo": record.id_externo,
        "numero_proposta": numero,
        "titulo": _titulo(dados, record, numero=numero, objeto=objeto, modalidade=modalidade),
        "objeto": objeto,
        "descricao": descricao,
        "orgao_superior": _texto(_pick(dados, _CANDIDATOS["orgao_superior"])),
        "modalidade": modalidade,
        "ano": ano,
        "municipio_ibge": record.municipio_ibge
        or _texto(_pick(dados, _CANDIDATOS["municipio_ibge"])),
        "municipio_nome": _texto(_pick(dados, _CANDIDATOS["municipio_nome"])),
        "uf": _texto(_pick(dados, _CANDIDATOS["uf"])),
        "valor_total": valor_total,
        "contrapartida": _to_decimal(_pick(dados, _CONTRAPARTIDA)),
        "situacao": _texto(_pick(dados, _CANDIDATOS["situacao"])),
        "emenda": _texto(_pick(dados, _CANDIDATOS["emenda"])),
        "prazos": None,
        "pendencias": None,
        "movimentacao": None,
        "data_atualizacao_fonte": data_fonte,
        "url_origem": _texto(_pick(dados, _CANDIDATOS["url_origem"])),
        "execucao": execucao,
    }

    # fim de vigência vira prazo estruturado (alimenta /proposals/deadlines)
    fim_vigencia = _to_date((execucao or {}).get("data_fim_vigencia"))
    if fim_vigencia:
        fields["prazos"] = [{"tipo": "fim de vigência", "data_limite": fim_vigencia.isoformat()}]

    # proveniência por-campo: registros vindos de scraper marcam 'scrape'
    origem = "scrape" if record.endpoint in ("scrape", "firecrawl", "crawl4ai") else "api"
    proveniencia = {k: origem for k, v in fields.items() if v is not None}
    proveniencia["_fonte"] = record.source_id
    fields["proveniencia"] = proveniencia
    fields["hash_conteudo"] = compute_hash(fields)

    return PropostaCanonica(**fields)
