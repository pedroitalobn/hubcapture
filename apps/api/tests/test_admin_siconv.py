"""Rotas de operação do pacote SIconv (admin).

O pacote é o ÚNICO caminho para as discricionárias/legais completas — a fonte
não publica consulta por município. Estas rotas são o que o operador tem para
ver o estado real dos arquivos e disparar a carga sem esperar a madrugada.

O que se protege aqui: catálogo honesto (indisponível ≠ ausente), recorte
validado antes de baixar centenas de MB, e a carga rodando FORA do request.
"""

from __future__ import annotations

import asyncio

import pytest

from src.api.v1 import admin_siconv
from src.connectors import siconv_downloads
from src.db.session import plataforma_session
from src.jobs import siconv_diario


async def _listar(monkeypatch, disponibilidades):
    async def _inspecionar_todos(tabelas=None):
        return disponibilidades

    monkeypatch.setattr(siconv_downloads, "inspecionar_todos", _inspecionar_todos)
    async with plataforma_session() as session:
        return await admin_siconv.listar_arquivos(_admin=None, session=session)


def _disp(tabela="proposta", **kw):
    base = dict(
        tabela=tabela,
        descricao="…",
        carrega=True,
        nome=f"siconv_{tabela}.zip",
        url=f"https://x/{tabela}.zip",
        disponivel=True,
        tamanho=1234,
        erro=None,
    )
    base.update(kw)
    return siconv_downloads.Disponibilidade(**base)


async def test_catalogo_mostra_o_estado_real_de_cada_arquivo(monkeypatch):
    catalogo = await _listar(monkeypatch, [_disp("proposta"), _disp("emenda", tamanho=99)])

    assert catalogo.base_url.startswith("http")
    assert [a.tabela for a in catalogo.arquivos] == ["proposta", "emenda"]
    assert catalogo.arquivos[0].disponivel and catalogo.arquivos[0].tamanho == 1234
    # o operador precisa saber o recorte antes de disparar
    assert catalogo.escopo_propostas in (
        siconv_diario.ESCOPO_TERRITORIO,
        siconv_diario.ESCOPO_NACIONAL,
    )
    assert catalogo.tabelas_da_carga


async def test_arquivo_indisponivel_aparece_com_o_motivo(monkeypatch):
    """ "A fonte renomeou o arquivo" e "a fonte caiu" precisam ser
    distinguíveis na tela — some da lista, ninguém descobre nem um nem outro."""
    catalogo = await _listar(
        monkeypatch,
        [_disp("pagamento", nome=None, disponivel=False, tamanho=None, erro="nenhum candidato")],
    )
    arquivo = catalogo.arquivos[0]
    assert arquivo.disponivel is False and arquivo.erro == "nenhum candidato"


async def test_catalogo_conta_o_territorio_monitorado(monkeypatch, seed_user, seed_municipio):
    """É o recorte da carga no escopo padrão: zero município = carga vazia, e o
    operador tem que ver isso ANTES de estranhar o resultado."""
    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await seed_municipio(uid, "3550308")

    catalogo = await _listar(monkeypatch, [_disp()])
    assert catalogo.municipios_monitorados == 2


async def test_disparo_recusa_tabela_fora_do_catalogo(monkeypatch):
    from fastapi import HTTPException

    from src.schemas.siconv import PedidoCarga

    chamou = False

    async def _sweep(tabelas=None):
        nonlocal chamou
        chamou = True
        return {}

    monkeypatch.setattr(siconv_diario, "sweep", _sweep)
    with pytest.raises(HTTPException) as erro:
        await admin_siconv.disparar_carga(
            PedidoCarga(tabelas=["proposta", "nao_existe"]), _admin=None
        )

    assert erro.value.status_code == 422
    assert "nao_existe" in erro.value.detail
    assert not chamou  # nada foi baixado


async def test_disparo_roda_em_segundo_plano_com_o_recorte_pedido(monkeypatch):
    """A carga leva minutos: ela não pode acontecer dentro do request (§19b)."""
    from src.schemas.siconv import PedidoCarga

    recebidas: list[tuple] = []
    terminou = asyncio.Event()

    async def _sweep(tabelas=None):
        recebidas.append(tabelas)
        terminou.set()
        return {"status": "ok"}

    monkeypatch.setattr(siconv_diario, "sweep", _sweep)
    resposta = await admin_siconv.disparar_carga(PedidoCarga(tabelas=["proposta"]), _admin=None)

    assert resposta.iniciada and resposta.tabelas == ["proposta"]
    await asyncio.wait_for(terminou.wait(), timeout=5)
    assert recebidas == [("proposta",)]


async def test_disparo_vazio_usa_o_recorte_agendado(monkeypatch):
    from src.schemas.siconv import PedidoCarga

    recebidas: list[tuple] = []
    terminou = asyncio.Event()

    async def _sweep(tabelas=None):
        recebidas.append(tabelas)
        terminou.set()
        return {}

    monkeypatch.setattr(siconv_diario, "sweep", _sweep)
    await admin_siconv.disparar_carga(PedidoCarga(tabelas=[]), _admin=None)
    await asyncio.wait_for(terminou.wait(), timeout=5)
    assert recebidas == [siconv_diario.tabelas_alvo()]


async def test_falha_da_carga_nao_derruba_o_processo(monkeypatch):
    """A task é órfã: sem o try/except o erro viraria 'Task exception was never
    retrieved' e sumiria."""
    from src.schemas.siconv import PedidoCarga

    tentou = asyncio.Event()

    async def _sweep(tabelas=None):
        tentou.set()
        raise RuntimeError("fonte fora do ar")

    monkeypatch.setattr(siconv_diario, "sweep", _sweep)
    await admin_siconv.disparar_carga(PedidoCarga(tabelas=["proposta"]), _admin=None)
    await asyncio.wait_for(tentou.wait(), timeout=5)
    await asyncio.sleep(0)  # deixa a task terminar sem levantar aqui


async def test_historico_traz_as_ultimas_cargas():
    from datetime import UTC, datetime

    from sqlalchemy import text

    from .conftest import _owner_engine

    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sync_runs (id, fonte, tipo, status, registros, iniciado_em, "
                "finalizado_em, erro) VALUES "
                "(gen_random_uuid(), 'siconv', 'agendado', 'ok', 42, :i, now(), NULL)"
            ),
            {"i": datetime.now(UTC)},
        )

    async with plataforma_session() as session:
        cargas = await admin_siconv.listar_cargas(limite=5, _admin=None, session=session)

    assert cargas and cargas[0].status == "ok" and cargas[0].registros == 42
