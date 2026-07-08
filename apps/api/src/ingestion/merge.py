"""Merge multi-fonte (scaffold do Sprint 1).

Precedência definida (seção 5.7 da arquitetura):
  - API vence: id_externo, valor_total, contrapartida, datas, numero_proposta.
  - Scraping vence (mais atual): situacao, pendencias, movimentacao.
Cada valor registra origem em `proveniencia`.

No Sprint 1 só existe API (`scrape=None`) → retorna a API pura. A estrutura de
precedência já está codificada para o Sprint futuro plugar o scraping.
"""

from __future__ import annotations

from ..schemas.proposta import PropostaCanonica

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
