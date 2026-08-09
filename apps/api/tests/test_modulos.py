"""Módulos da plataforma: defaults, toggle pelo admin e reflexo no perfil."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.db.session import SessionLocal, rls_session
from src.services import modulos as service
from src.services import perfil as perfil_service


async def _definir(chave: str, ativo: bool) -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, chave, ativo)


async def test_defaults_conformidade_e_obras_desativados() -> None:
    async with SessionLocal() as s:
        estado = await service.ativos(s)
    # recebidos nasce desligado por ora (foco na validação da Captação)
    assert estado["captacao"] and estado["copiloto"] and estado["ajuda"]
    assert not estado["recebidos"]
    assert not estado["conformidade"] and not estado["obras"]


async def test_definir_liga_e_desliga_persistindo() -> None:
    await _definir("obras", True)
    async with SessionLocal() as s:
        assert (await service.ativos(s))["obras"] is True
    await _definir("obras", False)  # upsert na mesma chave
    async with SessionLocal() as s:
        estado = await service.ativos(s)
        assert estado["obras"] is False
        itens = {m["chave"]: m for m in await service.listar(s)}
    assert itens["obras"]["ativo"] is False and itens["obras"]["padrao"] is False
    assert itens["captacao"]["ativo"] is True


async def test_require_modulo_404_quando_desativado() -> None:
    dep = service.require_modulo("obras")
    with pytest.raises(HTTPException) as exc:
        await dep()
    assert exc.value.status_code == 404
    await _definir("obras", True)
    await dep()  # ativo → não levanta


async def test_perfil_expoe_modulos_ativos(seed_user, seed_municipio) -> None:
    u = await seed_user("mod@a.com")
    await seed_municipio(u, "3550308")
    await _definir("conformidade", True)

    async with rls_session(u) as s:
        p = await perfil_service.get_perfil(s, _FakeUser(u))
    assert set(p.modulos) == {
        "captacao",
        "copiloto",
        "conformidade",
        "contatos",  # agenda de contatos nasce ligada
        "ajuda",  # central de ajuda nasce ligada
    }


class _FakeUser:
    def __init__(self, uid) -> None:
        self.id = uid
        self.papel = "executivo"
        self.nome = None
