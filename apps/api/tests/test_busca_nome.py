"""Busca tolerante de NOME (acento, caixa e erro de digitação).

Regressão do relato do gestor: digitar "apuiarez" no seletor de município
esvaziava a lista com Apuiarés no território. A regra mora em
`services/busca_nome.py` (e no espelho `apps/web/lib/busca.ts`); a busca de
municípios do onboarding (`services/municipios.buscar`) passa a usá-la quando
não há casamento exato.
"""

from __future__ import annotations

import pytest

from src.services import busca_nome
from src.services import municipios as municipios_service

_NOMES = [
    "Apuiarés/CE",
    "Mossoró/RN",
    "Xique-Xique/BA",
    "Itapajé/CE",
    "Itapipoca/CE",
    "São Gonçalo do Amarante/CE",
    "Fortaleza/CE",
    "Caucaia/CE",
    "Salto/SP",
    "São Paulo/SP",
    "Iguaçu/PR",
    "Belém/PA",
    "Juazeiro do Norte/CE",
]


def _filtrar(termo: str) -> list[str]:
    return busca_nome.filtrar(_NOMES, termo, busca_nome.preparar)


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        # o caso do relato: z no lugar de s, sem acento
        ("apuiarez", "Apuiarés/CE"),
        ("apuiaréz/ce", "Apuiarés/CE"),
        # letra que falta, letra a mais, letras invertidas
        ("apuirés", "Apuiarés/CE"),
        ("apuiaress", "Apuiarés/CE"),
        ("apuiraes", "Apuiarés/CE"),
        ("caucia", "Caucaia/CE"),
        # trocas do português falado
        ("mosoro", "Mossoró/RN"),
        ("chique chique", "Xique-Xique/BA"),
        ("itapage", "Itapajé/CE"),
        ("fortalesa", "Fortaleza/CE"),
        ("iguassu", "Iguaçu/PR"),
        ("belen", "Belém/PA"),
        ("juaseiro", "Juazeiro do Norte/CE"),
        # ainda digitando: prefixo continua valendo
        ("apuiar", "Apuiarés/CE"),
        ("forta", "Fortaleza/CE"),
        # palavras fora de ordem / pulando o conectivo
        ("goncalo amarante", "São Gonçalo do Amarante/CE"),
    ],
)
def test_acha_com_erro_de_digitacao(digitado: str, esperado: str) -> None:
    assert _filtrar(digitado) == [esperado]


def test_exata_preserva_a_ordem_e_nao_traz_aproximada_de_brinde() -> None:
    # "sao" casa exato com os dois "São …": "Salto" (a uma letra) NÃO entra
    assert _filtrar("sao") == ["São Gonçalo do Amarante/CE", "São Paulo/SP"]


def test_termo_curto_nao_tolera_erro() -> None:
    # com 3 letras, um erro casaria com meia lista
    assert _filtrar("xyz") == []
    assert _filtrar("qwertyuiop") == []


def test_sem_termo_devolve_tudo() -> None:
    assert _filtrar("  ") == _NOMES


def test_distancia_damerau() -> None:
    assert busca_nome.distancia("apuiares", "apuiares") == 0
    assert busca_nome.distancia("apuiraes", "apuiares") == 1  # transposição
    assert busca_nome.distancia("apuiars", "apuiares") == 1
    assert busca_nome.distancia("abc", "xyz", teto=1) == 2  # parou cedo


_MALHA_FAKE = [
    {"ibge": "2301208", "nome": "Apuiarés", "uf": "CE", "busca": "apuiares"},
    {"ibge": "2304400", "nome": "Fortaleza", "uf": "CE", "busca": "fortaleza"},
    {"ibge": "2408003", "nome": "Mossoró", "uf": "RN", "busca": "mossoro"},
]


async def test_busca_de_municipio_tolera_erro(monkeypatch) -> None:
    async def _carregar_fake() -> list[dict]:
        return _MALHA_FAKE

    monkeypatch.setattr(municipios_service, "_carregar", _carregar_fake)

    achados = await municipios_service.buscar("apuiarez")
    assert [m["ibge"] for m in achados] == ["2301208"]
    assert (await municipios_service.buscar("mosoro"))[0]["nome"] == "Mossoró"
    # o casamento exato continua mandando (prefixo antes de trecho)
    assert [m["ibge"] for m in await municipios_service.buscar("forta")] == ["2304400"]
    # nada parecido → vazio, não um município qualquer
    assert await municipios_service.buscar("qwertyuiop") == []
