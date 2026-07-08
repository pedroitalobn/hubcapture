"""Merge multi-fonte: precedência e proveniência."""

from __future__ import annotations

from decimal import Decimal

from src.ingestion.merge import merge
from src.schemas.proposta import PropostaCanonica


def _api() -> PropostaCanonica:
    return PropostaCanonica(
        fonte="transferegov_ff",
        id_externo="X1",
        valor_total=Decimal("100"),
        situacao="Em análise (D-1)",
        proveniencia={"valor_total": "api", "situacao": "api"},
    )


def test_merge_so_api_retorna_api() -> None:
    api = _api()
    out = merge(api, None)
    assert out is api
    assert out.proveniencia["situacao"] == "api"


def test_merge_scraping_vence_situacao_api_vence_valor() -> None:
    api = _api()
    scrape = PropostaCanonica(
        fonte="transferegov_ff",
        id_externo="X1",
        valor_total=Decimal("999"),  # deve ser IGNORADO (API vence em valor)
        situacao="Pendente (tempo real)",  # deve VENCER (scraping mais atual)
        movimentacao="Última movimentação hoje",
    )
    out = merge(api, scrape)
    assert out.valor_total == Decimal("100")  # API venceu
    assert out.situacao == "Pendente (tempo real)"  # scraping venceu
    assert out.movimentacao == "Última movimentação hoje"
    assert out.proveniencia["situacao"] == "scrape"
    assert out.proveniencia["movimentacao"] == "scrape"
    assert out.proveniencia["valor_total"] == "api"
