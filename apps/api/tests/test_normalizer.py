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


# ── Campos que chegavam vazios/errados ao painel ────────────────────────────
def test_objeto_e_descricao_se_cobrem() -> None:
    """A fonte que traz só a descrição do programa preenche os dois campos."""
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-1",
            raw={
                "programa": {
                    "nome_programa": "UBS",
                    "descricao_programa": "Construção de unidade básica de saúde",
                }
            },
        )
    )
    assert p.descricao == "Construção de unidade básica de saúde"
    assert p.objeto == p.descricao  # painel nunca mostra as duas linhas vazias


def test_titulo_cai_para_o_objeto_e_depois_para_o_numero() -> None:
    """Sem nome de programa a linha aparecia como '—'; agora sempre identifica."""
    so_objeto = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-2",
            raw={"plano_acao": {"objeto": "Reforma da escola municipal"}},
        )
    )
    assert so_objeto.titulo == "Reforma da escola municipal"

    so_numero = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-3",
            raw={"plano_acao": {"numero_plano_acao": "043210/2025"}},
        )
    )
    assert so_numero.titulo == "Fundo a Fundo 043210/2025"

    vazio = normalize(RawRecord(source_id="transferegov_ff", id_externo="PA-4", raw={}))
    assert vazio.titulo == "Fundo a Fundo PA-4"


def test_titulo_longo_e_truncado() -> None:
    objeto = "x" * 300
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-5",
            raw={"plano_acao": {"objeto": objeto}},
        )
    )
    assert len(p.titulo) == 120 and p.titulo.endswith("…")
    assert p.objeto == objeto  # o objeto completo permanece intacto


# ── Exercício (ano): o painel abre no ano corrente ──────────────────────────
def test_ano_vem_do_campo_do_plano() -> None:
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-6",
            raw={"plano_acao": {"ano_plano_acao": 2025}},
        )
    )
    assert p.ano == 2025


def test_ano_cai_para_o_numero_a_execucao_e_a_data() -> None:
    do_numero = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-7",
            raw={"plano_acao": {"numero_plano_acao": "043210/2024"}},
        )
    )
    assert do_numero.ano == 2024

    # o painel SERPRO só entrega o exercício dentro do bloco de execução
    da_execucao = normalize(
        RawRecord(
            source_id="serpro",
            id_externo="PA-8",
            endpoint="scrape",
            raw={"plano_acao": {"ano": "2026", "valor_global": "10"}},
        )
    )
    assert da_execucao.ano == 2026

    da_data = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-9",
            raw={"plano_acao": {"data_atualizacao": "2023-05-10"}},
        )
    )
    assert da_data.ano == 2023


# ── Variantes de nome de campo por fonte ────────────────────────────────────
def test_valor_total_soma_custeio_e_investimento() -> None:
    """O Fundo a Fundo não devolve total: entrega as duas parcelas separadas."""
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-10",
            raw={
                "plano_acao": {
                    "valor_custeio_plano_acao": "1000.50",
                    "valor_investimento_plano_acao": "500.50",
                }
            },
        )
    )
    assert p.valor_total == Decimal("1501.00")


def test_valor_em_formato_brasileiro() -> None:
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-11",
            raw={"plano_acao": {"valor_total": "1.234.567,89"}},
        )
    )
    assert p.valor_total == Decimal("1234567.89")


def test_csv_em_maiusculas_no_bloco_csv() -> None:
    """Colunas gritadas e fora do bloco `plano_acao` também são mapeadas."""
    p = normalize(
        RawRecord(
            source_id="transferegov_disc",
            id_externo="7788",
            municipio_ibge="3550308",
            raw={
                "csv": {
                    "NR_CONVENIO": "899123/2025",
                    "OBJETO_PROPOSTA": "Pavimentação de vias urbanas",
                    "DESC_ORGAO_SUPERIOR": "Ministério das Cidades",
                    "VL_GLOBAL": "250000.00",
                    "SITUACAO": "Em análise",
                }
            },
        )
    )
    assert p.numero_proposta == "899123/2025"
    assert p.titulo == "Pavimentação de vias urbanas"
    assert p.orgao_superior == "Ministério das Cidades"
    assert p.valor_total == Decimal("250000.00")
    assert p.situacao == "Em análise"
    assert p.modalidade == "Discricionária"
    assert p.ano == 2025


def test_plano_vence_o_programa_no_conflito() -> None:
    """O plano é o registro concreto; o programa é o guarda-chuva."""
    p = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="PA-12",
            raw={
                "plano_acao": {"situacao": "Aprovado", "ano_plano_acao": 2026},
                "programa": {"situacao": "Encerrado", "ano_programa": 2020},
            },
        )
    )
    assert p.situacao == "Aprovado"
    assert p.ano == 2026
