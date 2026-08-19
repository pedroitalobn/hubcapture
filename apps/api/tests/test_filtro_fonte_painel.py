"""Filtro global de FONTE do painel — grupo (TransfereGov | FNS) nos filtros.

O trilho lateral ganhou, abaixo do filtro de município, um recorte de fonte
para o usuário escolher de onde quer ver os dados. O usuário fala GRUPO
("transferegov", "fns" — §30), nunca connector id; os filtros `fonte` de
propostas, repasses e do feed do perfil passam a aceitar os dois vocabulários
via `fontes.expandir_filtro`.
"""

from __future__ import annotations

from datetime import date

from src.db.session import rls_session
from src.services import fontes as fontes_service
from src.services import perfil as perfil_service
from src.services import propostas as propostas_service
from src.services import repasses as repasses_service


class _FakeUser:
    def __init__(self, uid, papel: str = "executivo") -> None:
        self.id = uid
        self.papel = papel
        self.nome = None


def test_expandir_filtro_aceita_grupo_e_connector() -> None:
    # grupo → todos os connectors do grupo
    assert fontes_service.expandir_filtro("transferegov") == list(fontes_service.TRANSFEREGOV)
    assert fontes_service.expandir_filtro("fns") == ["fns"]
    # connector id continua valendo tal e qual
    assert fontes_service.expandir_filtro("transferegov_ff") == ["transferegov_ff"]
    # fonte fora do recorte (§30) segue filtrável no cache — volta como veio
    assert fontes_service.expandir_filtro("fpm") == ["fpm"]


async def test_propostas_filtram_por_grupo_de_fonte(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("fonte-prop@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "ff-1", "3550308", "Do FF")
    await seed_proposta("serpro", "vg-1", "3550308", "Da Visão Geral")
    await seed_proposta("fns", "fns-1", "3550308", "Do FNS")

    async with rls_session(u) as s:
        do_grupo = await propostas_service.listar(s, fonte="transferegov")
        do_fns = await propostas_service.listar(s, fonte="fns")
        exato = await propostas_service.listar(s, fonte="transferegov_ff")

    assert {p.titulo for p in do_grupo} == {"Do FF", "Da Visão Geral"}
    assert {p.titulo for p in do_fns} == {"Do FNS"}
    # o vocabulário antigo (connector id) não muda
    assert {p.titulo for p in exato} == {"Do FF"}


async def test_facetas_contam_sob_o_grupo_escolhido(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """As outras dimensões respeitam o recorte do grupo; a dimensão fonte segue
    ignorando o próprio filtro (senão o dropdown prenderia na escolha)."""
    u = await seed_user("fonte-facetas@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "ff-1", "3550308", situacao="Em análise")
    await seed_proposta("fns", "fns-1", "3550308", situacao="Paga")

    async with rls_session(u) as s:
        facetas = await propostas_service.facetas(s, fonte="transferegov")

    situacoes = {o["valor"]: o["total"] for o in facetas["situacao"]}
    assert situacoes == {"Em análise": 1}
    fontes = {o["valor"] for o in facetas["fonte"]}
    assert fontes == {"transferegov_ff", "fns"}  # ignora o próprio filtro


async def test_repasses_filtram_por_grupo_de_fonte(seed_user, seed_municipio, seed_repasse) -> None:
    u = await seed_user("fonte-rep@a.com")
    await seed_municipio(u, "3550308")
    await seed_repasse("fns", "r-fns", "3550308")
    await seed_repasse("fpm", "r-fpm", "3550308")

    async with rls_session(u) as s:
        do_grupo = await repasses_service.listar(s, fonte="fns")
        exato = await repasses_service.listar(s, fonte="fpm")

    assert {r.fonte for r in do_grupo} == {"fns"}
    assert {r.fonte for r in exato} == {"fpm"}


async def test_feed_recorta_pelo_grupo_de_fonte(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    """O Meu painel mistura captação (TransfereGov) e recebidos (FNS): o filtro
    global separa os dois lados sem mexer no recorte fino do perfil."""
    u = await seed_user("fonte-feed@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta(
        "transferegov_ff", "p-1", "3550308", "Proposta", data_proposta=date(2026, 3, 1)
    )
    await seed_repasse("fns", "r-1", "3550308", data_repasse="2026-02-10")

    async with rls_session(u) as s:
        tudo = await perfil_service.novidades(s, _FakeUser(u))
        so_fns = await perfil_service.novidades(s, _FakeUser(u), fonte="fns")
        so_tg = await perfil_service.novidades(s, _FakeUser(u), fonte="transferegov")

    assert {i.tipo for i in tudo.itens} == {"captacao", "recebido"}
    assert [(i.tipo, i.fonte) for i in so_fns.itens] == [("recebido", "fns")]
    assert [(i.tipo, i.fonte) for i in so_tg.itens] == [("captacao", "transferegov_ff")]
