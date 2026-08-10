"""Assessoria orçamentária: padrão versionado, edição pelo admin e link wa.me."""

from __future__ import annotations

from src.db.session import SessionLocal
from src.services import assessoria as service


async def test_padrao_versionado_com_link_whatsapp() -> None:
    async with SessionLocal() as s:
        contatos = await service.listar(s)
    assert [c["nome"] for c in contatos] == ["Raul", "Josué", "Diovany"]
    assert contatos[0]["whatsapp_url"] == "https://wa.me/5561982881163"
    assert contatos[1]["whatsapp_url"] == "https://wa.me/5561981009698"
    assert contatos[2]["whatsapp_url"] == "https://wa.me/5562982823332"


async def test_definir_substitui_a_lista_e_persiste() -> None:
    novos = [
        {"nome": "Ana", "telefone": "+55 11 91234-5678", "descricao": "Orçamento"},
    ]
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, novos)
    async with SessionLocal() as s:
        contatos = await service.listar(s)
    assert len(contatos) == 1
    assert contatos[0]["nome"] == "Ana"
    assert contatos[0]["descricao"] == "Orçamento"
    assert contatos[0]["whatsapp_url"] == "https://wa.me/5511912345678"

    # upsert na mesma chave: gravar de novo troca, não acumula
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, [c | {"nome": "Bia"} for c in novos])
    async with SessionLocal() as s:
        contatos = await service.listar(s)
    assert [c["nome"] for c in contatos] == ["Bia"]


def test_whatsapp_url_normaliza_ddi() -> None:
    # telefone sem DDI ganha o 55 do Brasil…
    assert service.whatsapp_url("(61) 98288-1163") == "https://wa.me/5561982881163"
    # …inclusive no DDD 55 (RS), que enganaria um startswith("55")
    assert service.whatsapp_url("55 99999-0000") == "https://wa.me/5555999990000"
    # com DDI já presente, nada muda
    assert service.whatsapp_url("+55 62 98282-3332") == "https://wa.me/5562982823332"
