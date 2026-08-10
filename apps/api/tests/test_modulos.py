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
    assert estado["assessoria"]
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
    # chamada direta (sem FastAPI): o default do parâmetro é o marcador
    # Depends — o gate de plano é pulado, como para request sem token.
    dep = service.require_modulo("obras")
    with pytest.raises(HTTPException) as exc:
        await dep()
    assert exc.value.status_code == 404
    await _definir("obras", True)
    await dep()  # ativo → não levanta


def test_gate_captacao_so_na_exploracao() -> None:
    """§40: o módulo captação guarda a EXPLORAÇÃO (filtros/facetas/relatório e
    live-search) — as leituras de cache que o Meu painel usa (resumo, prazos,
    detalhe, PDF) ficam fora do gate, senão desligar o módulo apaga o painel."""
    from src.api.v1 import consulta_avulsa as consulta_router
    from src.api.v1 import propostas as propostas_router

    def _tem_gate(deps) -> bool:
        return any(
            getattr(d.dependency, "__qualname__", "").startswith("require_modulo")
            for d in deps or []
        )

    gates = {
        r.path: _tem_gate(getattr(r, "dependencies", None))
        for r in propostas_router.router.routes
    }
    assert gates["/proposals"] and gates["/proposals/facets"]
    assert gates["/proposals/report.csv"]
    # panel-core: sempre disponíveis, com ou sem o módulo captação
    assert not gates["/proposals/summary"]
    assert not gates["/proposals/deadlines"]
    assert not gates["/proposals/{proposta_id}"]
    assert not gates["/proposals/{proposta_id}/pdf"]
    # a consulta ativa nas fontes é a essência do módulo — segue no gate
    assert _tem_gate(consulta_router.router.dependencies)


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
        "alertas",  # central de alertas nasce ligada
        "contatos",  # agenda de contatos nasce ligada
        "ajuda",  # central de ajuda nasce ligada
        "assessoria",  # assessoria orçamentária nasce ligada
    }


class _FakeUser:
    def __init__(self, uid) -> None:
        self.id = uid
        self.papel = "executivo"
        self.nome = None
