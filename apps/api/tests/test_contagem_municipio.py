"""Contagem por município: nenhuma linha some, nenhuma identidade oscila.

Regressão do relato do gestor: "Apuiarés aparece com 1 proposta (tipo scraping)
no ano de 2026, mas tinha 5" e "o número de propostas do município fica mudando".
São dois defeitos distintos e ambos ficam aqui:

1. `_combinada.aglutinar` DESCARTAVA linha de scraping sem número identificável
   sempre que alguma outra linha tinha número — 5 linhas da página viravam 1
   registro.
2. o `id_externo` de retaguarda era POSICIONAL (`i`, `len(records)+1`,
   `painel-{ibge}-{i}`) ou nem escopado no município (`str(None)`), e o par
   único (fonte, id_externo) é global: linhas se sobrescreviam entre coletas e
   entre territórios, mudando a contagem e o município da proposta.
"""

from __future__ import annotations

from src.connectors import _combinada, _identidade

# ── 1. Aglutinação não perde linha ──────────────────────────────────────────


def test_scraping_sem_numero_nao_e_descartado() -> None:
    """5 linhas na página → 5 registros, mesmo que só uma traga o número."""
    scrape = [
        {"numero": "901231/2024", "objeto": "com número"},
        {"objeto": "sem número 1"},
        {"objeto": "sem número 2"},
        {"objeto": "sem número 3"},
        {"objeto": "sem número 4"},
    ]

    pares = _combinada.aglutinar([], scrape)

    assert len(pares) == 5
    assert [p[1] for p in pares] == scrape  # todas, na ordem da página


def test_numero_repetido_na_pagina_nao_colapsa() -> None:
    """Duas linhas com o mesmo número são duas transferências, não uma."""
    scrape = [
        {"numero": "100/2026", "objeto": "parcela 1"},
        {"numero": "100/2026", "objeto": "parcela 2"},
    ]

    pares = _combinada.aglutinar([], scrape)

    assert len(pares) == 2
    assert {p[1]["objeto"] for p in pares} == {"parcela 1", "parcela 2"}


def test_api_consome_um_par_por_linha_de_scraping() -> None:
    """Duas linhas da API com o mesmo número casam com uma linha cada."""
    api = [{"numero_proposta": "100"}, {"numero_proposta": "100"}]
    scrape = [{"numero": "100", "situacao": "A"}, {"numero": "100", "situacao": "B"}]

    pares = _combinada.aglutinar(api, scrape)

    assert len(pares) == 2  # ninguém sobrou solto
    assert sorted(p[1]["situacao"] for p in pares) == ["A", "B"]


def test_scraping_sem_par_entra_sozinho_junto_do_pareado() -> None:
    api = [{"numero_proposta": "111", "valor": "10"}]
    scrape = [{"numero": "111", "situacao": "Em execução"}, {"objeto": "só na página"}]

    pares = _combinada.aglutinar(api, scrape)

    assert len(pares) == 2
    pareado = [p for p in pares if p[0]]
    assert pareado[0][1]["situacao"] == "Em execução"
    assert ({}, {"objeto": "só na página"}) in pares


# ── 2. Identidade estável e escopada no município ───────────────────────────


def test_id_de_conteudo_e_estavel_entre_coletas() -> None:
    """Mesma linha → mesmo id, mesmo que a fonte reordene as chaves."""
    linha = {"objeto": "UBS", "valor": "10", "situacao": "Nova"}
    embaralhada = {"situacao": "Nova", "valor": "10", "objeto": "UBS"}

    assert _identidade.hash_conteudo(linha, "2301109") == _identidade.hash_conteudo(
        embaralhada, "2301109"
    )


def test_id_de_conteudo_nao_colide_entre_municipios() -> None:
    """A linha "1" de um município não pode ser a "1" do outro (par único é global)."""
    linha = {"objeto": "UBS"}

    assert _identidade.hash_conteudo(linha, "2301109") != _identidade.hash_conteudo(
        linha, "3550308"
    )


def test_id_publicado_pela_fonte_vence_o_hash() -> None:
    row = {"ID_PROPOSTA": "34530", "objeto": "UBS"}

    assert _identidade.id_externo(row, "2301109", candidatos=("id_proposta",)) == "34530"


def test_id_ausente_nunca_vira_a_string_none() -> None:
    """`str(row.get("id"))` dava o id literal "None" — o mesmo para todo mundo."""
    a = _identidade.id_externo({"id": None, "objeto": "A"}, "2301109", candidatos=("id",))
    b = _identidade.id_externo({"id": "None", "objeto": "B"}, "2301109", candidatos=("id",))

    assert a != b
    assert "None" not in (a, b)
