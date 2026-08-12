"""Normalização do empenho: linha bruta → schema canônico.

Hash LOCAL sobre os campos materiais (número, data, valores, situação): é assim
que um reforço ou uma anulação viram mudança detectada. Reusar `compute_hash` de
`normalizer.py` daria o mesmo hash para todo empenho, como já aconteceu com
parecer e obra.

De-para por PALAVRA da coluna (`ingestion/_campos.py`) — o módulo nomeia com o
sufixo da entidade (`valor_empenhado_empenho_especial`) e a rota irmã encurta
para `valor_empenhado`.

ATENÇÃO ao valor: "empenhado" e "anulado" moram os dois em colunas que casam
`valor`. A ordem dos candidatos importa, e `anulado`/`cancelado` são EXCLUÍDOS
do candidato a empenhado — senão a anulação entraria como se fosse recurso
disponível, que é o oposto do que ela significa.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..schemas.empenho import EmpenhoCanonico
from ._campos import ano_de, data_de, decimal_br, por_termos, primeiro, texto
from .normalizer import _ci

_HASH_FIELDS = (
    "numero_empenho",
    "data_empenho",
    "tipo_empenho",
    "situacao",
    "valor_empenhado",
    "valor_anulado",
    "valor_liquidado",
    "valor_pago",
)

# um valor anulado/cancelado não é valor empenhado disponível
_NAO_EMPENHADO = ("anulado", "anulacao", "cancelado", "cancelamento", "estorno")


def _hash(data: dict[str, Any]) -> str:
    material = {k: data.get(k) for k in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def normalize_empenho(
    bruto: dict,
    *,
    fonte: str,
    numero_proposta: str | None = None,
    numero_plano_acao: str | None = None,
    municipio_ibge: str | None = None,
) -> EmpenhoCanonico:
    r = _ci(bruto)

    numero_empenho = texto(
        primeiro(
            por_termos(r, "numero", "empenho"),
            r.get("nr_empenho"),
            r.get("ne"),
            por_termos(r, "empenho", "documento"),
        )
    )
    data_empenho = data_de(
        primeiro(
            por_termos(r, "data", "empenho"),
            r.get("data_emissao"),
            por_termos(r, "data", "emissao"),
        )
    )

    fields: dict[str, Any] = {
        "fonte": fonte,
        "numero_proposta": texto(primeiro(por_termos(r, "numero", "proposta"), numero_proposta)),
        "numero_plano_acao": texto(
            primeiro(r.get("id_plano_acao"), r.get("numero_plano_acao"), numero_plano_acao)
        ),
        "municipio_ibge": municipio_ibge,
        "numero_empenho": numero_empenho,
        "data_empenho": data_empenho,
        "tipo_empenho": texto(primeiro(por_termos(r, "tipo", "empenho"), r.get("especie"))),
        "situacao": texto(primeiro(por_termos(r, "situacao"), r.get("status"))),
        "ano": (
            str(ano_de(primeiro(por_termos(r, "ano"), data_empenho)) or "") or None
        ),
        # empenhado: nunca casa uma coluna de anulação/estorno
        "valor_empenhado": decimal_br(
            primeiro(
                por_termos(r, "valor", "empenhado", excluir=_NAO_EMPENHADO),
                por_termos(r, "valor", "empenho", excluir=_NAO_EMPENHADO),
                r.get("valor"),
            )
        ),
        "valor_anulado": decimal_br(
            primeiro(por_termos(r, "valor", "anulado"), por_termos(r, "valor", "cancelado"))
        ),
        "valor_liquidado": decimal_br(por_termos(r, "valor", "liquidado")),
        "valor_pago": decimal_br(por_termos(r, "valor", "pago")),
        "ug_emitente": texto(primeiro(por_termos(r, "ug"), por_termos(r, "unidade", "gestora"))),
        "gestao_emitente": texto(por_termos(r, "gestao")),
        "natureza_despesa": texto(
            primeiro(por_termos(r, "natureza", "despesa"), por_termos(r, "natureza"))
        ),
        "fonte_recurso": texto(primeiro(por_termos(r, "fonte", "recurso"), r.get("fonte_recurso"))),
        "programa_trabalho": texto(por_termos(r, "programa", "trabalho")),
        "observacao": texto(primeiro(por_termos(r, "observacao"), por_termos(r, "descricao"))),
        "detalhe": bruto,
    }

    # Identidade: o id da fonte manda; sem ele, o número do empenho (que é único
    # por UG/ano) e, em último caso, a chave sintética proposta|numero|data.
    fields["id_externo"] = str(
        primeiro(
            por_termos(r, "id", "empenho"),
            r.get("id"),
            numero_empenho,
            "|".join(
                str(x or "")
                for x in (
                    fields["numero_proposta"] or fields["numero_plano_acao"],
                    data_empenho.isoformat() if data_empenho else "",
                    fields["valor_empenhado"] or "",
                )
            ),
        )
    )

    fields["proveniencia"] = {k: "api" for k, v in fields.items() if v is not None}
    fields["proveniencia"]["_fonte"] = fonte
    fields["hash_conteudo"] = _hash(fields)

    return EmpenhoCanonico(**fields)
