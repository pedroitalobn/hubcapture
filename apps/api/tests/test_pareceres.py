"""Pareceres do plano de trabalho — normalização, identidade e hash.

Testes sem banco: cobrem o que decide se o dado entra certo (de-para de campos,
identidade estável entre syncs, detecção de mudança) e o elo proposta → plano de
trabalho. A COLETA em si não é testada aqui: rota e schema de extração ainda
estão por calibrar contra a fonte viva (§36).
"""

from __future__ import annotations

from datetime import date

from src.connectors.base import RawRecord
from src.ingestion.normalizer import normalize
from src.ingestion.normalizer_parecer import normalize_parecer

# a linha como a tela de tramitação a entrega (o que o gestor vê)
LINHA = {
    "data": "01/06/2026",
    "esfera": "CONCEDENTE",
    "responsavel": "RENATA OLIVEIRA",
    "papel": "Gestor de Instrumento do Concedente",
    "cargo": "COORDENADORA-GERAL",
    "url_parecer": "https://exemplo.gov.br/parecer/1",
}


def _norm(linha: dict, **kw):
    base = dict(numero_plano_trabalho="14275/2026", fonte="transferegov_parecer")
    return normalize_parecer(linha, **{**base, **kw})


def test_le_a_linha_da_tramitacao() -> None:
    p = _norm(LINHA)
    assert p.data_parecer == date(2026, 6, 1)
    assert p.esfera == "concedente"
    assert p.responsavel == "RENATA OLIVEIRA"
    assert p.papel == "Gestor de Instrumento do Concedente"
    assert p.cargo == "COORDENADORA-GERAL"
    assert p.url_parecer == "https://exemplo.gov.br/parecer/1"
    assert p.numero_plano_trabalho == "14275/2026"


def test_le_cabecalho_em_caixa_alta() -> None:
    """A fonte manda CAIXA ALTA (§35) — o de-para tem que casar mesmo assim."""
    p = _norm({"DATA": "28/05/2026", "ESFERA": "CONCEDENTE", "RESPONSAVEL": "NATALI GOMES"})
    assert p.data_parecer == date(2026, 5, 28)
    assert p.responsavel == "NATALI GOMES"


def test_identidade_estavel_entre_syncs() -> None:
    """Mesma linha coletada de novo = mesmo id_externo, senão duplica no upsert."""
    assert _norm(LINHA).id_externo == _norm(dict(LINHA)).id_externo


def test_pareceres_diferentes_nao_colidem() -> None:
    """Duas linhas do mesmo plano em datas/pessoas diferentes são registros distintos."""
    outro = {**LINHA, "data": "28/05/2026", "responsavel": "NATALI GOMES"}
    assert _norm(LINHA).id_externo != _norm(outro).id_externo


def test_mesma_pessoa_mesmo_dia_papeis_diferentes_nao_colidem() -> None:
    # a amostra real traz linhas repetidas por papel — o papel entra na identidade
    outro = {**LINHA, "papel": "Analista Técnico do Concedente"}
    assert _norm(LINHA).id_externo != _norm(outro).id_externo


def test_hash_muda_quando_o_parecer_muda() -> None:
    igual = _norm(dict(LINHA))
    assert _norm(LINHA).hash_conteudo == igual.hash_conteudo
    mudou = _norm({**LINHA, "situacao": "Aprovado com ressalvas"})
    assert mudou.hash_conteudo != igual.hash_conteudo


def test_hash_e_proprio_do_parecer() -> None:
    """Regressão: reusar `compute_hash` da proposta daria hash igual p/ todos."""
    a = _norm(LINHA)
    b = _norm({**LINHA, "responsavel": "OUTRA PESSOA"})
    assert a.hash_conteudo != b.hash_conteudo


def test_proveniencia_marca_scraping() -> None:
    assert _norm({**LINHA, "_scraper": "playwright"}).proveniencia["responsavel"] == "scrape"
    assert _norm(LINHA).proveniencia["responsavel"] == "api"


def test_guarda_a_linha_bruta_para_calibracao() -> None:
    p = _norm({**LINHA, "COLUNA_DESCONHECIDA": "valor"})
    assert p.detalhe["COLUNA_DESCONHECIDA"] == "valor"


def test_proposta_carrega_o_numero_do_plano_de_trabalho() -> None:
    """O elo: sem ele a tela não sabe por qual número consultar o parecer."""
    p = normalize(
        RawRecord(
            source_id="transferegov_voluntarias",
            id_externo="C-1",
            municipio_ibge="3550308",
            raw={"NR_PROPOSTA": "14275/2026", "NR_PLANO_TRABALHO": "988776"},
        )
    )
    assert p.numero_plano_trabalho == "988776"
    assert p.numero_proposta == "14275/2026"
