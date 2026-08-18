"""Diretório institucional — gabinetes, chefias, assessorias e SEIs (ponto 19).

Lista CURADA de nível-plataforma: mesma para todos os clientes, editada pelo
painel admin, sem migration (mecânica do `services/assessoria`). O que os testes
travam: o saneamento não deixa lixo entrar, a busca alcança o número do SEI
(é com ele na mão que o gestor procura), e valor corrompido no banco degrada
para lista vazia em vez de derrubar a tela.
"""

from __future__ import annotations

from sqlalchemy import text

from src.db.session import SessionLocal
from src.services import contatos_institucionais as service

from .conftest import _owner_engine

ENTRADAS = [
    {
        "nome": "Gabinete do Ministro",
        "orgao": "Ministério da Saúde",
        "cargo": "Chefia de Gabinete",
        "categoria": "chefia_gabinete",
        "email": "gabinete@saude.gov.br",
        "telefone": "61 3315-2425",
        "sei": "25000.123456/2026-11",
    },
    {
        "nome": "Assessoria Parlamentar",
        "orgao": "Ministério da Educação",
        "categoria": "assessoria_parlamentar",
        "telefone": "6120228000",
    },
]


async def _definir(entradas: list[dict]) -> None:
    async with SessionLocal() as s:
        await service.definir(s, entradas)
        await s.commit()


async def test_lista_vazia_sem_nada_gravado() -> None:
    """Sem curadoria ainda, a aba é vazia — não é erro nem lista de exemplo."""
    async with SessionLocal() as s:
        assert await service.listar(s) == []


async def test_grava_e_le_o_diretorio() -> None:
    await _definir(ENTRADAS)
    async with SessionLocal() as s:
        itens = await service.listar(s)
    assert len(itens) == 2
    # ordenado por órgão: Educação antes de Saúde
    assert itens[0]["orgao"] == "Ministério da Educação"
    assert itens[0]["categoria_rotulo"] == "Assessoria parlamentar"


async def test_whatsapp_so_quando_ha_telefone() -> None:
    await _definir([{"nome": "Gabinete X", "orgao": "MS"}, ENTRADAS[0]])
    async with SessionLocal() as s:
        por_nome = {c["nome"]: c for c in await service.listar(s)}
    assert por_nome["Gabinete X"]["whatsapp_url"] is None
    assert por_nome["Gabinete do Ministro"]["whatsapp_url"].startswith("https://wa.me/55")


async def test_busca_alcanca_o_numero_do_sei() -> None:
    """O gestor tem o protocolo na mão e quer saber com quem falar sobre ele."""
    await _definir(ENTRADAS)
    async with SessionLocal() as s:
        achados = await service.listar(s, q="25000.123456")
    assert len(achados) == 1
    assert achados[0]["orgao"] == "Ministério da Saúde"


async def test_busca_ignora_acento_e_caixa() -> None:
    await _definir(ENTRADAS)
    async with SessionLocal() as s:
        assert len(await service.listar(s, q="MINISTERIO DA EDUCACAO")) == 1


async def test_filtra_por_categoria() -> None:
    await _definir(ENTRADAS)
    async with SessionLocal() as s:
        assert len(await service.listar(s, categoria="chefia_gabinete")) == 1
        assert await service.listar(s, categoria="gabinete_ministro") == []


async def test_categoria_desconhecida_vira_outros() -> None:
    """Lista curada é digitada à mão — categoria errada não pode virar 500."""
    await _definir([{**ENTRADAS[0], "categoria": "inventada"}])
    async with SessionLocal() as s:
        assert (await service.listar(s))[0]["categoria"] == "outros"


async def test_entrada_sem_nome_e_sem_orgao_e_descartada() -> None:
    await _definir([{"telefone": "6133152425"}, ENTRADAS[1]])
    async with SessionLocal() as s:
        assert len(await service.listar(s)) == 1


async def test_valor_corrompido_no_banco_degrada_para_vazio() -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO configuracoes (chave, valor, secreto, cifrado, categoria) "
                "VALUES ('contatos_institucionais', '{isso não é json', false, false, 'contatos')"
            )
        )
    async with SessionLocal() as s:
        assert await service.listar(s) == []
