"""Flag de versão de UI (porte v2 → v1): catálogo, sanitização e resolução."""

from __future__ import annotations

from src.api.v1.ui import versao_ui_efetiva
from src.db.session import SessionLocal
from src.services import config as service


def test_ui_versao_esta_no_catalogo() -> None:
    assert service.chave_valida("ui_versao") is True


def test_sanitizacao_so_aceita_versoes_conhecidas() -> None:
    # sem config (None/vazio) → v2, a UI atual
    assert versao_ui_efetiva(None) == "v2"
    assert versao_ui_efetiva("") == "v2"
    # valores válidos, com folga de caixa/espaço (digitado no painel)
    assert versao_ui_efetiva("v1") == "v1"
    assert versao_ui_efetiva(" V1 ") == "v1"
    assert versao_ui_efetiva("v2") == "v2"
    # config inválida nunca quebra a plataforma → cai na v2
    assert versao_ui_efetiva("v3") == "v2"
    assert versao_ui_efetiva("clássica") == "v2"


async def test_flag_gravada_pelo_painel_resolve() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, "ui_versao", "v1")
        async with s.begin():
            assert versao_ui_efetiva(await service.get_valor(s, "ui_versao")) == "v1"
