"""Filtro de ano do Meu painel — uma safra para a página inteira.

O painel tinha dois filtros de ano com critérios diferentes: o gráfico do
panorama pedia a safra à API e o feed classificava por conta própria, pela data
da COLETA. Resultado: filtrar o ano ajustava o gráfico e deixava os cards e as
novidades noutro recorte, com item de 2019 aparecendo como novidade do ano
corrente. Aqui garantimos o contrário: `visao_geral` e `novidades` respondem à
MESMA safra (`ano_de` na captação, ano do pagamento nos recebidos), a ordem é
por safra decrescente e as opções do filtro não somem quando um ano é escolhido.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from src.db.session import SessionLocal, rls_session
from src.services import modulos as modulos_service
from src.services import perfil as service


class _FakeUser:
    """Stand-in do modelo Usuario (só os atributos que o serviço lê)."""

    def __init__(self, uid, papel: str = "executivo") -> None:
        self.id = uid
        self.papel = papel
        self.nome = None


async def _ligar_recebidos() -> None:
    """Recebidos nasce desligado (§29) — o teste liga p/ exercitar a dimensão."""
    async with SessionLocal() as s:
        async with s.begin():
            await modulos_service.definir(s, "recebidos", True)


async def test_feed_usa_a_safra_da_proposta_e_nao_a_data_da_coleta(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """A novidade vale pelo ano da PROPOSTA. Pela data de coleta (todas de
    hoje), uma proposta de 2019 entrava no feed como novidade do ano corrente."""
    u = await seed_user("safra@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta(
        "transferegov_ff", "velha", "3550308", "Velha", data_proposta=date(2019, 5, 2)
    )
    await seed_proposta(
        "transferegov_ff", "nova", "3550308", "Nova", data_proposta=date(2026, 3, 7)
    )

    async with rls_session(u) as s:
        nov = await service.novidades(s, _FakeUser(u))

    # ordem: safra decrescente (o "mostrar todos" do painel)
    assert [(i.titulo, i.ano) for i in nov.itens] == [("Nova", "2026"), ("Velha", "2019")]
    # a data exibida é a da própria proposta, não a da coleta (hoje)
    assert [i.data for i in nov.itens] == [date(2026, 3, 7), date(2019, 5, 2)]


async def test_feed_filtra_pela_safra_escolhida(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await seed_user("safra2@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "p2024", "3550308", data_proposta=date(2024, 8, 1))
    await seed_proposta("transferegov_ff", "p2026", "3550308", data_proposta=date(2026, 1, 9))
    await seed_repasse("fpm", "r2024", "3550308", data_repasse="2024-02-10")
    await seed_repasse("fpm", "r2026", "3550308", data_repasse="2026-02-10")

    async with rls_session(u) as s:
        nov = await service.novidades(s, _FakeUser(u), ano="2024")

    assert nov.itens, "a safra escolhida tem itens"
    assert {i.ano for i in nov.itens} == {"2024"}
    # o filtro não pode apagar as próprias opções: `anos` continua com o
    # território inteiro, senão o usuário fica preso na safra que escolheu
    assert [a.ano for a in nov.anos] == ["2026", "2024"]


async def test_feed_alcanca_safra_antiga_fora_da_janela(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """O recorte é do servidor, ANTES da janela: escolher 2019 traz o item de
    2019 mesmo que a janela só coubesse as novidades mais recentes."""
    u = await seed_user("janela@a.com")
    await seed_municipio(u, "3550308")
    for i in range(5):
        await seed_proposta(
            "transferegov_ff", f"nova{i}", "3550308", data_proposta=date(2026, 3, 7)
        )
    await seed_proposta("transferegov_ff", "antiga", "3550308", data_proposta=date(2019, 5, 2))

    async with rls_session(u) as s:
        recentes = await service.novidades(s, _FakeUser(u), limite=3)
        antiga = await service.novidades(s, _FakeUser(u), limite=3, ano="2019")

    assert {i.ano for i in recentes.itens} == {"2026"}  # a janela só alcança 2026
    assert [i.ano for i in antiga.itens] == ["2019"]  # e a safra escolhida, não


async def test_visao_geral_recorta_as_dimensoes_com_safra(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    """Os CARDS acompanham o filtro — captação pela safra da proposta,
    recebidos pelo ano do pagamento."""
    u = await seed_user("cards@a.com")
    await seed_municipio(u, "3550308")
    await _ligar_recebidos()
    await seed_proposta(
        "transferegov_ff",
        "c2024",
        "3550308",
        data_proposta=date(2024, 8, 1),
        valor_total=Decimal("10"),
    )
    await seed_proposta(
        "transferegov_ff",
        "c2026",
        "3550308",
        data_proposta=date(2026, 1, 9),
        valor_total=Decimal("20"),
    )
    await seed_repasse("fpm", "r2024", "3550308", valor="500", data_repasse="2024-02-10")
    await seed_repasse("fpm", "r2026", "3550308", valor="700", data_repasse="2026-02-10")

    async with rls_session(u) as s:
        todos = await service.visao_geral(s, _FakeUser(u))
        safra = await service.visao_geral(s, _FakeUser(u), ano="2024")

    assert {d.chave: d.total for d in todos.dimensoes} == {"captacao": 2, "recebidos": 2}
    dims = {d.chave: d for d in safra.dimensoes}
    assert dims["captacao"].total == 1
    assert dims["recebidos"].total == 1
    # a safra viaja para a exploração: o card leva a captação já filtrada
    assert dims["captacao"].href == "/panel/funding?ano=2024"
    assert all(q.href.endswith("&ano=2024") for q in dims["captacao"].quebras)


async def test_visao_geral_marca_dimensao_sem_safra(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Conformidade e obras são o estado ATUAL do município — a dimensão diz
    que ignora o ano em vez de fingir um recorte que não existe."""
    u = await seed_user("semsafra@a.com")
    await seed_municipio(u, "3550308")
    async with SessionLocal() as s:
        async with s.begin():
            await modulos_service.definir(s, "obras", True)
    await seed_proposta("transferegov_ff", "c1", "3550308", data_proposta=date(2024, 8, 1))

    async with rls_session(u) as s:
        vg = await service.visao_geral(s, _FakeUser(u), ano="2024")

    dims = {d.chave: d for d in vg.dimensoes}
    assert dims["captacao"].recorte_ano is True
    assert dims["obras"].recorte_ano is False


async def test_feed_usa_ano_prop_quando_nao_ha_data_da_proposta(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Mesmo critério do resto do app: sem `data_proposta`, a safra vem do
    ANO_PROP do registro-fonte (`propostas.ano_de`)."""
    u = await seed_user("anoprop@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta(
        "transferegov_ff",
        "so_ano_prop",
        "3550308",
        dados_fonte=json.dumps({"ano_prop": "2023"}),
    )

    async with rls_session(u) as s:
        nov = await service.novidades(s, _FakeUser(u), ano="2023")

    assert [i.ano for i in nov.itens] == ["2023"]


async def test_painel_soma_varias_safras(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    """Multi-seleção de safra: escolher 2024 E 2026 soma os recortes — o feed
    traz os itens dos dois anos e os cards contam os dois, deixando 2025 fora."""
    u = await seed_user("multisafra@a.com")
    await seed_municipio(u, "3550308")
    await _ligar_recebidos()
    await seed_proposta("transferegov_ff", "p2024", "3550308", data_proposta=date(2024, 8, 1))
    await seed_proposta("transferegov_ff", "p2025", "3550308", data_proposta=date(2025, 4, 2))
    await seed_proposta("transferegov_ff", "p2026", "3550308", data_proposta=date(2026, 1, 9))
    await seed_repasse("fpm", "r2024", "3550308", data_repasse="2024-02-10")
    await seed_repasse("fpm", "r2025", "3550308", data_repasse="2025-02-10")

    async with rls_session(u) as s:
        nov = await service.novidades(s, _FakeUser(u), ano=["2024", "2026"])
        vg = await service.visao_geral(s, _FakeUser(u), ano=["2024", "2026"])

    assert {i.ano for i in nov.itens} == {"2024", "2026"}
    assert {d.chave: d.total for d in vg.dimensoes} == {"captacao": 2, "recebidos": 1}
    # as safras viajam para a exploração como parâmetro repetido (§33)
    dims = {d.chave: d for d in vg.dimensoes}
    assert dims["captacao"].href == "/panel/funding?ano=2024&ano=2026"
    assert all(q.href.endswith("&ano=2024&ano=2026") for q in dims["captacao"].quebras)


# ── recorte dos CARDS financeiros (ponto 06 do feedback) ────────────────────
async def test_cards_do_painel_recortam_o_feed(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    """Clicar em "Empenhado" lista as propostas que compõem aquele número.

    Antes, o card era leitura pura: o gestor lia "R$ 4,95 mi empenhado" e não
    tinha caminho nenhum para as propostas por trás do valor.
    """
    u = await seed_user("cards@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta(
        "transferegov_ff",
        "com-empenho",
        "3550308",
        "Com empenho",
        data_proposta=date(2026, 2, 1),
        execucao=json.dumps({"valor_empenhado": "500000.00"}),
    )
    await seed_proposta(
        "transferegov_ff",
        "publicada",
        "3550308",
        "Publicada",
        data_proposta=date(2026, 2, 2),
        execucao=json.dumps({"situacao_publicacao": "Publicado"}),
    )
    await seed_proposta(
        "transferegov_ff",
        "paga",
        "3550308",
        "Paga",
        data_proposta=date(2026, 2, 3),
        execucao=json.dumps({"valor_pago": "120000.00"}),
    )
    await seed_repasse("fpm", "r1", "3550308", data_repasse="2026-02-10")

    async def titulos(session, recorte: str) -> set[str]:
        feed = await service.novidades(session, _FakeUser(u), estado=recorte)
        return {i.titulo for i in feed.itens}

    async with rls_session(u) as s:
        assert await titulos(s, "empenhado") == {"Com empenho"}
        assert await titulos(s, "publicado") == {"Publicada"}
        assert await titulos(s, "pago") == {"Paga"}
        # sem recorte, tudo volta — inclusive o repasse (que não tem empenho
        # nem publicação e por isso fica de fora quando há recorte)
        completo = await service.novidades(s, _FakeUser(u))
        assert len(completo.itens) == 4


async def test_recorte_desconhecido_nao_esvazia_o_painel(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Valor novo vindo do front não pode zerar a tela do gestor."""
    u = await seed_user("cards2@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "p1", "3550308", data_proposta=date(2026, 2, 1))
    async with rls_session(u) as s:
        nov = await service.novidades(s, _FakeUser(u), estado="inventado")
    assert len(nov.itens) == 1
