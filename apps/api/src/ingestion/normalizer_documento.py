"""Normalização do documento digitalizado: linha da lista → schema canônico.

A ESPÉCIE do documento é derivada do NOME do arquivo, porque é só isso que a
fonte publica: "Publicação 999293.pdf", "PM_Apuiares_-_1109227-74_-_Oficio_de_
Celebracao_ao_Legislativo_assinado.pdf", "..._Contrato_de_Repasse_assinado.pdf".
A derivação é o que permite a tela responder "cadê o documento da publicação?"
sem obrigar o gestor a ler a lista inteira — e é calibrável numa tabela só.

O de-para é por PALAVRA do nome (sem acento, sem separador), nunca por
substring solta: "termo" está dentro de "determinação", e "ato" dentro de
"contrato". Nome que não casa nada vira `outro` — nunca um palpite.

Hash LOCAL sobre nome + data + url: republicação do mesmo documento (a fonte
troca o arquivo mantendo o nome) vira mudança detectada.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from ..schemas.documento import DocumentoCanonico
from ._campos import data_de, texto
from .normalizer import _ci

_HASH_FIELDS = ("nome", "data_upload", "url")

# espécie → palavras que a identificam no nome do arquivo. A ordem importa:
# "Publicação do Contrato de Repasse" é, para o gestor, a PUBLICAÇÃO.
_ESPECIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("publicacao", ("publicacao", "publicado", "dou", "extrato")),
    ("contrato", ("contrato", "convenio", "repasse")),
    ("oficio", ("oficio", "ofc", "encaminhamento")),
    ("projeto", ("projeto", "basico", "referencia", "memorial", "planilha", "orcamento")),
    ("termo", ("termo", "aditivo", "apostilamento")),
    ("parecer", ("parecer", "analise")),
    ("plano", ("plano", "trabalho", "cronograma")),
)

_SEPARADORES = re.compile(r"[^a-z0-9]+")


def _palavras(nome: str) -> set[str]:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome.lower()) if unicodedata.category(c) != "Mn"
    )
    return {p for p in _SEPARADORES.split(sem_acento) if p}


def classificar(nome: str | None) -> str:
    """Espécie do documento a partir do nome do arquivo."""
    palavras = _palavras(nome or "")
    if not palavras:
        return "outro"
    for especie, marcadores in _ESPECIES:
        if palavras & set(marcadores):
            return especie
    return "outro"


def _hash(data: dict[str, Any]) -> str:
    material = {k: data.get(k) for k in _HASH_FIELDS}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def normalize_documento(
    bruto: dict,
    *,
    fonte: str,
    id_proposta_fonte: str | None = None,
    numero_proposta: str | None = None,
    municipio_ibge: str | None = None,
) -> DocumentoCanonico | None:
    """Linha da lista → canônico. Sem NOME não há documento: devolve `None`.

    Linha sem nome é cabeçalho, rodapé ou lixo de layout — entrar no cache como
    um documento sem identidade daria ao gestor um item que ele não consegue
    nem pedir ao órgão.
    """
    r = _ci(bruto)
    nome = texto(r.get("nome") or r.get("nome_arquivo") or r.get("arquivo"))
    if not nome:
        return None

    url = texto(r.get("url") or r.get("link") or r.get("href"))
    data_upload = data_de(r.get("data_upload") or r.get("data") or r.get("data_up"))

    # Identidade: o id que a fonte publica para o arquivo; sem ele, a proposta
    # + o nome. Índice de posição NÃO serve — a lista reordena entre coletas e
    # o mesmo documento trocaria de identidade a cada rodada (§51).
    id_fonte = texto(r.get("id_arquivo") or r.get("id_documento") or r.get("id"))
    id_externo = id_fonte or f"{id_proposta_fonte or numero_proposta or 'sp'}:{nome}"

    dados = {
        "fonte": fonte,
        "id_externo": id_externo[:128],
        "numero_proposta": numero_proposta,
        "id_proposta_fonte": id_proposta_fonte,
        "municipio_ibge": municipio_ibge,
        "nome": nome,
        "tipo": classificar(nome),
        "data_upload": data_upload,
        "url": url,
        "detalhe": {k: v for k, v in bruto.items() if not str(k).startswith("_")} or None,
        "proveniencia": {"nome": "scrape", "url": "scrape", "data_upload": "scrape"},
    }
    dados["hash_conteudo"] = _hash(dados)
    return DocumentoCanonico(**dados)
