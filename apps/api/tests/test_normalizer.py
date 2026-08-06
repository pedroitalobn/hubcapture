"""Normalização: mapeamento canônico + hash determinístico."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.connectors.base import RawRecord
from src.ingestion.normalizer import compute_hash, normalize


def _record(situacao: str = "Em análise", **plano_extra) -> RawRecord:
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
                **plano_extra,
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


def test_ano_vem_da_criacao_e_nao_da_atualizacao() -> None:
    """Proposta criada em 2022 com movimentação em 2026 continua sendo de 2022."""
    p = normalize(
        _record(
            data_proposta="2022-03-14",
            data_atualizacao="2026-01-30",
            numero_plano_acao="043210/2022",
        )
    )
    assert p.data_criacao_fonte == date(2022, 3, 14)
    assert p.data_atualizacao_fonte == date(2026, 1, 30)
    assert p.ano == 2022


def test_ano_cai_para_campo_de_ano_da_fonte() -> None:
    """Sem data de criação, vale o ano cheio da fonte — nunca a atualização."""
    p = normalize(_record(ano_plano_acao="2023", data_atualizacao="2026-01-30"))
    assert p.data_criacao_fonte is None
    assert p.ano == 2023


def test_ano_cai_para_sufixo_do_numero_da_proposta() -> None:
    """Último recurso: 'NNNNNN/AAAA' carrega o ano de criação no sufixo."""
    p = normalize(_record(data_atualizacao="2026-01-30"))  # nº = 043210/2025
    assert p.ano == 2025


def test_ano_ignora_valor_implausivel() -> None:
    p = normalize(_record(numero_plano_acao="000001/1970", ano_proposta="1889"))
    assert p.ano is None


def test_ano_nao_entra_no_hash() -> None:
    """`ano` é imutável: entrar no hash geraria alerta falso em toda proposta."""
    p1 = normalize(_record(ano_proposta="2022"))
    p2 = normalize(_record(ano_proposta="2024"))
    assert p1.ano == 2022 and p2.ano == 2024
    assert p1.hash_conteudo == p2.hash_conteudo


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
