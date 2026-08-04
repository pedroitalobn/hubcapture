"""Merge multi-fonte — API e scraping aglutinados num registro só.

Precedência definida (seção 5 da arquitetura):
  - API vence: id_externo, valor_total, contrapartida, datas, numero_proposta.
  - Scraping vence (mais atual): situacao, pendencias, movimentacao.
Cada valor registra origem em `proveniencia`.

`merge_record` é a porta de entrada do pipeline: o connector que roda os dois
lados (ver `connectors/_combinada.py`) devolve o payload de scraping dentro do
próprio `raw`, sob a chave `_scrape`, e aqui os dois viram `PropostaCanonica` e
se fundem. Connector de um lado só continua funcionando igual — sem `_scrape`,
`merge_record` é `normalize` puro.
"""

from __future__ import annotations

from dataclasses import replace

from ..connectors._combinada import CHAVE_SCRAPE
from ..connectors.base import RawRecord
from ..schemas.proposta import PropostaCanonica
from .normalizer import normalize

# campos onde o scraping vence em conflito (mais atual que a API D-1)
SCRAPE_WINS = ("situacao", "pendencias", "movimentacao")


def merge(
    api: PropostaCanonica | None,
    scrape: PropostaCanonica | None = None,
) -> PropostaCanonica:
    if api is not None and scrape is None:
        return api
    if api is None and scrape is not None:
        return scrape
    if api is None and scrape is None:
        raise ValueError("merge chamado sem nenhuma fonte")

    # ambos presentes → aplica precedência por campo
    assert api is not None and scrape is not None
    data = api.model_dump()
    proveniencia = dict(api.proveniencia or {})
    for k in SCRAPE_WINS:
        v = getattr(scrape, k)
        if v not in (None, "", []):
            data[k] = v
            proveniencia[k] = "scrape"
    # campos exclusivos do scraping entram como vierem
    for k, v in scrape.model_dump().items():
        if data.get(k) in (None, "", []) and v not in (None, "", []):
            data[k] = v
            proveniencia[k] = "scrape"
    data["proveniencia"] = proveniencia
    return PropostaCanonica(**data)


def merge_record(record: RawRecord) -> PropostaCanonica:
    """RawRecord (com ou sem payload de scraping) → proposta canônica aglutinada.

    O lado de scraping vira um RawRecord irmão com `endpoint="scrape"` — é isso
    que faz o normalizador marcar `proveniencia = 'scrape'` nos campos que vieram
    da página, e o merge saber quem tem autoridade sobre cada campo.
    """
    raw = dict(record.raw or {})
    payload_scrape = raw.pop(CHAVE_SCRAPE, None)
    if not payload_scrape:
        return merge(normalize(record), None)

    lado_api = normalize(replace(record, raw=raw)) if raw else None
    lado_scrape = normalize(replace(record, raw=payload_scrape, endpoint="scrape"))
    return merge(lado_api, lado_scrape)
