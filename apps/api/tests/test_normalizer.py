"""Normalização: mapeamento canônico + hash determinístico."""

from __future__ import annotations

from decimal import Decimal

from src.connectors.base import RawRecord
from src.ingestion.normalizer import compute_hash, normalize


def _record(situacao: str = "Em análise") -> RawRecord:
    return RawRecord(
        source_id="transferegov_ff",
        id_externo="PA-123",
        municipio_ibge="3550308",
        raw={
            "plano_acao": {
                "numero_plano_acao": "043210/2025",
                "valor_total": "1500000.00",
                "valor_contrapartida": "50000.00",
                "situacao": situacao,
                "id_programa": 9,
            },
            "programa": {
                "nome_programa": "Ampliação de UBS",
                "nome_orgao_superior_programa": "Ministério da Saúde",
            },
            "beneficiario": {
                "nome_municipio": "São Paulo",
                "sigla_uf": "SP",
                "id_programa": 9,
            },
        },
    )


def test_normalize_mapeia_campos_canonicos() -> None:
    p = normalize(_record())
    assert p.fonte == "transferegov_ff"
    assert p.id_externo == "PA-123"
    assert p.numero_proposta == "043210/2025"
    assert p.titulo == "Ampliação de UBS"
    assert p.orgao_superior == "Ministério da Saúde"
    assert p.municipio_ibge == "3550308"
    assert p.municipio_nome == "São Paulo"
    assert p.uf == "SP"
    assert p.valor_total == Decimal("1500000.00")
    assert p.contrapartida == Decimal("50000.00")
    assert p.situacao == "Em análise"
    # proveniência: no Sprint 1 tudo vem da API
    assert p.proveniencia is not None
    assert p.proveniencia["valor_total"] == "api"
    assert p.proveniencia["_fonte"] == "transferegov_ff"


def test_normalize_mapeia_nr_proposta_do_csv() -> None:
    """transferegov_disc não tem API: o número vem do NR_PROPOSTA do CSV."""
    p = normalize(
        RawRecord(
            source_id="transferegov_disc",
            id_externo="1234567",
            municipio_ibge="2304400",
            raw={
                "csv": {"NR_PROPOSTA": "043210/2025", "COD_IBGE": "2304400"},
                "modalidade": "Discricionária",
            },
        )
    )
    assert p.numero_proposta == "043210/2025"


def test_normalize_numero_sempre_string() -> None:
    """Fonte JSON pode devolver o número como inteiro — o canônico é texto."""
    p = normalize(
        RawRecord(
            source_id="fnde",
            id_externo="X",
            municipio_ibge="3550308",
            raw={"nr_proposta": 987654},
        )
    )
    assert p.numero_proposta == "987654"


def test_hash_deterministico_e_sensivel_a_mudanca() -> None:
    p1 = normalize(_record(situacao="Em análise"))
    p2 = normalize(_record(situacao="Em análise"))
    assert p1.hash_conteudo == p2.hash_conteudo  # mesmo input → mesmo hash

    p3 = normalize(_record(situacao="Aprovada"))
    assert p3.hash_conteudo != p1.hash_conteudo  # mudança material → hash diferente


def test_compute_hash_ignora_campos_nao_materiais() -> None:
    base = {"situacao": "X", "valor_total": Decimal("1")}
    h1 = compute_hash({**base, "id": "aaa"})
    h2 = compute_hash({**base, "id": "bbb"})
    assert h1 == h2  # 'id' não entra no hash
