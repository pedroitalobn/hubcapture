"""Classificador determinístico de categorias (as pílulas do painel).

Sem rede e sem banco: é a camada que garante pílula em TODA proposta, mesmo com
a IA desligada. Os casos abaixo saíram de registros reais do TransfereGov.
"""

from __future__ import annotations

from src.ai import categorias as cat


def test_classifica_pelos_textos_da_proposta() -> None:
    assert cat.classificar("Pavimentação em Paralelepípedo da Rua Prefeito") == ["infraestrutura"]
    assert cat.classificar("Aquisição de ambulância para a UBS", "Ministério da Saúde") == ["saude"]
    assert "esporte" in cat.classificar("Construção de Quadra Coberta Poliesportiva")
    assert "cultura" in cat.classificar("MTUR/SECULT - ALDIR BLANC - MUNICÍPIOS")


def test_casa_por_palavra_e_nao_por_substring() -> None:
    """'agriCULTURA' não é Cultura e 'SUStentável' não é SUS — o erro clássico."""
    assert cat.classificar("Feiras da Agricultura Familiar dos produtores rurais") == [
        "agricultura"
    ]
    assert "saude" not in cat.classificar("Projeto de desenvolvimento sustentável")


def test_sem_texto_ou_sem_tema_nao_inventa_pilula() -> None:
    assert cat.classificar(None, "") == []
    assert cat.classificar("Termo aditivo nº 3 ao instrumento") == []


def test_no_maximo_tres_pilulas_mais_forte_primeiro() -> None:
    slugs = cat.classificar(
        "Construção de quadra esportiva escolar com posto de saúde e pavimentação",
        limite=3,
    )
    assert len(slugs) <= 3
    assert len(set(slugs)) == len(slugs)


def test_sanear_descarta_o_que_a_ia_inventar() -> None:
    assert cat.sanear(["saude", "categoria_inexistente", "saude", "cultura"]) == [
        "saude",
        "cultura",
    ]
    assert cat.sanear("saude") == []  # string não é lista de slugs
    assert cat.sanear(None) == []


def test_rotular_entrega_slug_e_rotulo() -> None:
    assert cat.rotular(["saude", "xx"]) == [{"slug": "saude", "rotulo": "Saúde"}]
    assert cat.rotular(None) == []


def test_taxonomia_integra() -> None:
    """Slug único, rótulo preenchido — a taxonomia é contrato de filtro."""
    assert len(cat.SLUGS) == len(set(cat.SLUGS))
    assert all(cat.ROTULOS[s] for s in cat.SLUGS)
