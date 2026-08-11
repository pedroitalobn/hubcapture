"""Normalização da emenda parlamentar: linha bruta → schema canônico.

Mesma disciplina de `normalizer_parecer`/`normalizer_obra`: hash LOCAL sobre os
campos materiais da emenda (`compute_hash` de `normalizer.py` filtra pelos
campos da PROPOSTA — reusá-lo aqui daria o mesmo hash para toda emenda e
nenhuma mudança de empenho seria detectada). Reusa dali só o `_ci`, porque a
fonte manda cabeçalho em CAIXA ALTA (§35).

O de-para é por CANDIDATOS e por SUFIXO: o módulo especiais nomeia as colunas
com o sufixo da entidade (`nome_parlamentar_emenda_plano_acao`), e uma rota
irmã pode chamar a mesma coisa de `nome_parlamentar`. Em vez de listar todas as
combinações, procura-se a chave que contenha os termos — o que a fonte chamar de
"parlamentar" entra como parlamentar.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from ..schemas.emenda import EmendaCanonica
from .normalizer import _ci

_HASH_FIELDS = (
    "codigo_emenda",
    "numero_emenda",
    "ano",
    "tipo_emenda",
    "parlamentar",
    "partido",
    "valor",
    "valor_empenhado",
    "valor_pago",
    "situacao",
)

# termos que NÃO podem casar quando se procura o NOME do parlamentar (um código
# ou um tipo casaria "parlamentar" e viraria o autor na tela)
_RUIDO_NOME = ("codigo", "cod", "id", "tipo", "quantidade", "qtd")


def _hash(data: dict[str, Any]) -> str:
    material = {k: data.get(k) for k in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def _texto(v: Any) -> str | None:
    if v in (None, "", [], {}):
        return None
    return " ".join(str(v).split()) or None


def _decimal(v: Any) -> Decimal | None:
    if v in (None, "", []):
        return None
    bruto = str(v).strip().replace("R$", "").strip()
    # "1.234.567,89" (fonte em pt-BR) → "1234567.89"
    if "," in bruto and re.search(r",\d{1,2}$", bruto):
        bruto = bruto.replace(".", "").replace(",", ".")
    bruto = bruto.replace(" ", "")
    try:
        return Decimal(bruto)
    except (InvalidOperation, ValueError):
        return None


def _inteiro(v: Any) -> int | None:
    achado = re.search(r"\d{4}", str(v or ""))
    return int(achado.group()) if achado else None


def _palavras(chave: str) -> set[str]:
    """Quebra a coluna em PALAVRAS: `valor_emenda_plano_acao` → {valor, emenda,
    plano, acao}. Casar por substring aqui é armadilha — "ano" está dentro de
    "plano", e `id_emenda_plano_acao` virava o ano da emenda."""
    return {p for p in re.split(r"[^a-z0-9]+", chave.lower()) if p}


def _por_termos(
    linha: dict, *termos: str, excluir: tuple[str, ...] = (), primeiro: bool = True
) -> Any:
    """Primeiro valor cuja CHAVE tenha todas as palavras (e nenhuma excluída)."""
    achados = []
    for chave, valor in linha.items():
        if not isinstance(chave, str) or valor in (None, "", [], {}):
            continue
        palavras = _palavras(chave)
        if palavras.issuperset(termos) and not palavras.intersection(excluir):
            achados.append(valor)
    if not achados:
        return None
    return achados[0] if primeiro else achados


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def normalize_emenda(
    bruto: dict,
    *,
    fonte: str,
    numero_plano_acao: str | None = None,
    numero_proposta: str | None = None,
    municipio_ibge: str | None = None,
) -> EmendaCanonica:
    r = _ci(bruto)

    parlamentar = _texto(
        _first(
            _por_termos(r, "nome", "parlamentar", excluir=_RUIDO_NOME),
            _por_termos(r, "parlamentar", excluir=_RUIDO_NOME),
            r.get("nome_autor"),
            r.get("autor"),
            _por_termos(r, "autor", excluir=_RUIDO_NOME),
        )
    )
    numero_emenda = _texto(
        _first(
            _por_termos(r, "numero", "emenda"),
            r.get("nr_emenda"),
            r.get("numero_emenda"),
        )
    )
    codigo_emenda = _texto(
        _first(
            _por_termos(r, "codigo", "emenda"),
            r.get("codigo_emenda"),
            r.get("cod_emenda"),
        )
    )

    fields: dict[str, Any] = {
        "fonte": fonte,
        "numero_plano_acao": _texto(
            _first(
                r.get("id_plano_acao"),
                r.get("numero_plano_acao"),
                numero_plano_acao,
            )
        ),
        "numero_proposta": _texto(_first(r.get("numero_proposta"), numero_proposta)),
        "municipio_ibge": municipio_ibge,
        "codigo_emenda": codigo_emenda,
        "numero_emenda": numero_emenda,
        "ano": _inteiro(_first(_por_termos(r, "ano", "emenda"), r.get("ano"))),
        "tipo_emenda": _texto(
            _first(_por_termos(r, "tipo", "emenda"), r.get("modalidade"))
        ),
        "parlamentar": parlamentar,
        "partido": _texto(
            _first(_por_termos(r, "partido"), r.get("sigla_partido"), r.get("partido"))
        ),
        "uf_parlamentar": _texto(
            _first(_por_termos(r, "uf", "parlamentar"), _por_termos(r, "uf", "autor"))
        ),
        "cargo_parlamentar": _texto(
            _first(_por_termos(r, "cargo"), _por_termos(r, "casa"), r.get("tipo_autor"))
        ),
        "codigo_parlamentar": _texto(
            _first(
                _por_termos(r, "codigo", "parlamentar"),
                _por_termos(r, "id", "parlamentar"),
            )
        ),
        "valor": _decimal(
            _first(
                _por_termos(r, "valor", "emenda"),
                _por_termos(r, "valor", "repasse"),
                r.get("valor"),
            )
        ),
        "valor_empenhado": _decimal(
            _first(_por_termos(r, "valor", "empenhado"), r.get("empenhado"))
        ),
        "valor_pago": _decimal(_first(_por_termos(r, "valor", "pago"), r.get("pago"))),
        "funcao": _texto(_first(_por_termos(r, "funcao"), r.get("area"))),
        "situacao": _texto(_first(_por_termos(r, "situacao"), r.get("status"))),
        "url_origem": _first(r.get("url_origem"), r.get("link"), r.get("url")),
        "detalhe": bruto,
    }

    # Identidade: o id da fonte manda. Sem ele (caso do registro-fonte, que só
    # carrega os campos da emenda dentro do plano de ação), a chave sintética
    # plano|emenda|parlamentar mantém o upsert estável entre coletas.
    fields["id_externo"] = str(
        _first(
            _por_termos(r, "id", "emenda", "plano"),
            r.get("id_emenda"),
            r.get("id"),
            codigo_emenda,
            "|".join(
                str(x or "")
                for x in (
                    fields["numero_plano_acao"] or fields["numero_proposta"],
                    numero_emenda or "",
                    (parlamentar or "").lower(),
                )
            ),
        )
    )

    origem = "registro_fonte" if bruto.get("_origem") == "registro_fonte" else "api"
    fields["proveniencia"] = {k: origem for k, v in fields.items() if v is not None}
    fields["proveniencia"]["_fonte"] = fonte
    fields["hash_conteudo"] = _hash(fields)

    return EmendaCanonica(**fields)
