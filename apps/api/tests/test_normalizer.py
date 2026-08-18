"""Normalização: mapeamento canônico + hash determinístico."""

from __future__ import annotations

from datetime import date
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


def test_valor_em_formato_br() -> None:
    rec = _record()
    rec.raw["plano_acao"]["valor_total"] = "1.500.000,00"
    rec.raw["plano_acao"]["valor_contrapartida"] = "1.234,56"
    p = normalize(rec)
    assert p.valor_total == Decimal("1500000.00")
    assert p.contrapartida == Decimal("1234.56")


def test_valor_total_soma_custeio_e_investimento_das_especiais() -> None:
    # especiais sem campo de total: pegar só investimento OU custeio subestima
    rec = RawRecord(
        source_id="transferegov_esp",
        id_externo="E-1",
        municipio_ibge="3550308",
        raw={
            "plano_acao": {
                "numero_plano_acao": "000001/2025",
                "valor_investimento_plano_acao": "1.000.000,50",
                "valor_custeio_plano_acao": "500,50",
                "situacao": "Aprovada",
            }
        },
    )
    p = normalize(rec)
    assert p.valor_total == Decimal("1000501.00")


def _record_csv(**plano) -> RawRecord:
    """Linha do CSV do SIconv como o connector do disc entrega (de-para + bruta)."""
    return RawRecord(
        source_id="transferegov_disc",
        id_externo="34530",
        municipio_ibge="2304400",
        raw={"plano_acao": plano, "modalidade": "Discricionária"},
    )


def test_nr_proposta_vem_da_linha_bruta_quando_o_de_para_nao_casa() -> None:
    """Bug real: NR_PROPOSTA visível no registro-fonte e proposta 'sem número'.

    O connector guarda a linha original em `csv` ao lado do de-para. Quando o
    de-para não casa a coluna, o valor segue lá — e é de lá que ele tem de sair,
    senão o painel exibe "sem número na fonte" com o número na própria tela.
    """
    p = normalize(
        _record_csv(
            nr_proposta=None,  # de-para não achou a coluna
            numero="700123/2009",  # nº do CONVÊNIO — não é a referência da proposta
            csv={"NR_PROPOSTA": "34530/2009", "DESC_ORGAO": "MINISTERIO DO TURISMO"},
        )
    )
    assert p.numero_proposta == "34530/2009"
    assert p.orgao_superior == "MINISTERIO DO TURISMO"  # mesma retaguarda


def test_de_para_do_connector_vence_a_linha_bruta() -> None:
    p = normalize(_record_csv(nr_proposta="999/2020", csv={"NR_PROPOSTA": "111/1999"}))
    assert p.numero_proposta == "999/2020"


def test_data_proposta_remontada_da_linha_bruta() -> None:
    p = normalize(
        _record_csv(csv={"NR_PROPOSTA": "34530/2009", "DIA_PROP": "3", "MES_PROP": "7",
                         "ANO_PROP": "2009"})
    )
    assert p.data_proposta == date(2009, 7, 3)


def test_publicado_entra_na_execucao_como_valor_e_como_situacao() -> None:
    """"Publicado" (pontos 08/13) vem da fonte nos dois sentidos — o de-para
    aceita os dois, e quem escolhe o que exibir é a tela."""
    from src.ingestion.normalizer import _montar_execucao

    exec_valor = _montar_execucao({"VL_PUBLICADO": "1500,00"})
    assert exec_valor and exec_valor["valor_publicado"] == "1500,00"

    exec_situacao = _montar_execucao({"PUBLICACAO": "Publicado"})
    assert exec_situacao and exec_situacao["situacao_publicacao"] == "Publicado"
