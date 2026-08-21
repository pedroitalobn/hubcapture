"""Filtro de ORIGEM DO RECURSO do painel — ver só o que veio de certas fontes.

O trilho oferece a origem em GRUPO ("TransfereGov", "FNS"), que é o vocabulário
do gestor (§30); o banco guarda connector id. O recorte precisa atravessar as
lentes — captação, recebidos e o Meu painel (visão geral + feed) —, senão
marcar FNS "não faz nada" numa tela e filtra noutra.

Nada aqui amplia visibilidade: o RLS continua sendo o limite.
"""

from __future__ import annotations

from src.db.session import rls_session
from src.services import fontes as fontes_service
from src.services import perfil as perfil_service
from src.services import propostas as prop_service
from src.services import repasses as rep_service


# ── normalização do filtro (pura, sem banco) ────────────────────────────────
def test_grupo_expande_para_todos_os_connectors_do_grupo() -> None:
    # o erro que a tela cometia: "TransfereGov" filtrando por UM connector só
    assert fontes_service.connectors("transferegov") == list(fontes_service.TRANSFEREGOV)
    assert fontes_service.connectors(["fns"]) == list(fontes_service.FNS)
    # grupos somados, sem duplicata e na ordem da escolha
    assert fontes_service.connectors(["fns", "transferegov", "fns"]) == [
        *fontes_service.FNS,
        *fontes_service.TRANSFEREGOV,
    ]
    # connector id continua valendo (link antigo, chamada direta)
    assert fontes_service.connectors(["transferegov_disc"]) == ["transferegov_disc"]
    # nada escolhido = sem recorte, nunca "nenhuma fonte"
    assert fontes_service.connectors(None) == []
    assert fontes_service.connectors([]) == []
    assert fontes_service.connectors(["", "  "]) == []


def test_fonte_fora_do_recorte_da_v1_ainda_e_filtravel() -> None:
    """`expandir` governa a COLETA; o filtro é leitura do que já está no cache."""
    assert fontes_service.expandir(["fpm"]) == []
    assert fontes_service.connectors(["fpm"]) == ["fpm"]


def test_origens_do_perfil_sao_grupos_e_nao_connectors() -> None:
    chaves = [o["chave"] for o in fontes_service.origens_do_perfil(["transferegov_ff", "fns"])]
    assert chaves == ["transferegov", "fns"]
    # perfil sem fonte gravada enxerga o catálogo INTEIRO (filtro vazio é pior
    # que filtro amplo) — e acompanha o catálogo, não uma lista fixa: grupo novo
    # (o FNDE foi o último) entra no trilho sem tocar aqui
    assert [o["chave"] for o in fontes_service.origens_do_perfil(None)] == list(
        fontes_service.GRUPOS
    )
    # só um grupo escolhido → só ele no trilho
    assert [o["chave"] for o in fontes_service.origens_do_perfil(["fns_propostas"])] == ["fns"]


def test_rotulo_do_connector_nunca_e_o_slug() -> None:
    assert fontes_service.rotulo_connector("transferegov_disc") == "TransfereGov — Discricionárias"
    assert fontes_service.rotulo_connector("fns_propostas") == "FNS — Fundo Nacional de Saúde"
    assert fontes_service.rotulo_connector(None) == ""


async def _territorio(seed_user, seed_municipio, seed_proposta, seed_repasse, email: str):
    """Município com propostas das duas origens e repasses do FNS."""
    u = await seed_user(email)
    await seed_municipio(u, "2300705")
    await seed_proposta("transferegov_disc", "TG1", "2300705", "Pavimentação de vias")
    await seed_proposta("fns_propostas", "FNS1", "2300705", "Custeio PAP")
    await seed_repasse("fns", "R1", "2300705", valor="500")
    return u


# ── captação ────────────────────────────────────────────────────────────────
async def test_captacao_filtra_pelo_grupo_escolhido(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await _territorio(seed_user, seed_municipio, seed_proposta, seed_repasse, "orig1@x.com")

    async with rls_session(u) as s:
        assert {p.id_externo for p in await prop_service.listar(s)} == {"TG1", "FNS1"}
        # o grupo FNS pesca `fns_propostas` — era isto que a tela errava ao
        # filtrar pelo id do grupo cru
        assert [p.id_externo for p in await prop_service.listar(s, fonte=["fns"])] == ["FNS1"]
        # e TransfereGov pesca o CSV das discricionárias, não só o fundo a fundo
        assert [p.id_externo for p in await prop_service.listar(s, fonte=["transferegov"])] == [
            "TG1"
        ]
        # somar os dois grupos = o território inteiro
        assert {
            p.id_externo for p in await prop_service.listar(s, fonte=["transferegov", "fns"])
        } == {"TG1", "FNS1"}
        # connector id direto continua funcionando
        assert [p.id_externo for p in await prop_service.listar(s, fonte="transferegov_disc")] == [
            "TG1"
        ]


async def test_facetas_contam_o_recorte_do_grupo(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await _territorio(seed_user, seed_municipio, seed_proposta, seed_repasse, "orig2@x.com")

    async with rls_session(u) as s:
        facetas = await prop_service.facetas(s, fonte=["fns"])
        # a dimensão fonte ignora o próprio filtro (senão o dropdown fecharia
        # em cima da opção escolhida)
        assert {o["valor"] for o in facetas["fonte"]} == {"transferegov_disc", "fns_propostas"}
        # o rótulo é o nome da fonte, nunca o slug do connector
        assert {o["rotulo"] for o in facetas["fonte"]} == {
            "TransfereGov — Discricionárias",
            "FNS — Fundo Nacional de Saúde",
        }
        # as demais dimensões SIM enxergam o recorte da origem
        assert [o["valor"] for o in facetas["municipio"]] == ["2300705"]
        assert sum(o["total"] for o in facetas["municipio"]) == 1


# ── recebidos ───────────────────────────────────────────────────────────────
async def test_recebidos_filtram_kpi_e_feed_juntos(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await _territorio(seed_user, seed_municipio, seed_proposta, seed_repasse, "orig3@x.com")
    await seed_repasse("fpm", "R2", "2300705", valor="700")

    async with rls_session(u) as s:
        assert {r.id_externo for r in await rep_service.listar(s)} == {"R1", "R2"}
        assert [r.id_externo for r in await rep_service.listar(s, fonte=["fns"])] == ["R1"]

        # o KPI acompanha o feed: filtrar só a lista no cliente deixava o total
        # pago contando origem que o gestor tinha tirado da tela
        vg = await rep_service.visao_geral(s, fonte=["fns"])
        assert vg.movimentacoes == 1
        assert str(vg.total_pago) == "500.00"
        assert [f.fonte for f in vg.fontes] == ["fns"]


# ── Meu painel (visão geral + feed) ─────────────────────────────────────────
async def test_visao_geral_e_feed_seguem_a_origem(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    u = await _territorio(seed_user, seed_municipio, seed_proposta, seed_repasse, "orig4@x.com")

    async with rls_session(u) as s:
        usuario = await _usuario(s, u)

        visao = await perfil_service.visao_geral(s, usuario)
        dim = {d.chave: d.total for d in visao.dimensoes}
        assert dim["captacao"] == 2 and dim["recebidos"] == 1

        visao_fns = await perfil_service.visao_geral(s, usuario, fontes_filtro=["fns"])
        dim_fns = {d.chave: d.total for d in visao_fns.dimensoes}
        assert dim_fns["captacao"] == 1 and dim_fns["recebidos"] == 1

        visao_tg = await perfil_service.visao_geral(s, usuario, fontes_filtro=["transferegov"])
        dim_tg = {d.chave: d.total for d in visao_tg.dimensoes}
        # TransfereGov não produz repasse neste território: a dimensão zera em
        # vez de continuar contando o que veio do FNS
        assert dim_tg["captacao"] == 1 and dim_tg.get("recebidos", 0) == 0

        feed = await perfil_service.novidades(s, usuario)
        assert {i.fonte for i in feed.itens} == {"transferegov_disc", "fns_propostas", "fns"}

        # o filtro do trilho vale para os DOIS eixos do feed
        feed_fns = await perfil_service.novidades(s, usuario, fontes_filtro=["fns"])
        assert {i.fonte for i in feed_fns.itens} == {"fns_propostas", "fns"}

        feed_tg = await perfil_service.novidades(s, usuario, fontes_filtro=["transferegov"])
        assert {i.fonte for i in feed_tg.itens} == {"transferegov_disc"}


async def test_feed_nomeia_fonte_e_municipio(
    seed_user, seed_municipio, seed_proposta, seed_repasse
) -> None:
    """A linha do feed não mostra slug de integração nem município sem nome (§35)."""
    u = await seed_user("orig5@x.com")
    await seed_municipio(u, "2300705")
    await seed_proposta("transferegov_disc", "TG1", "2300705", "Pavimentação")
    # o repasse costuma chegar da fonte SEM município resolvido — o feed
    # mostrava a linha inteira sem território
    await seed_repasse("fns", "R1", "2300705", valor="500")

    async with rls_session(u) as s:
        feed = await perfil_service.novidades(s, await _usuario(s, u))
        rotulos = {i.fonte: i.fonte_rotulo for i in feed.itens}
        assert rotulos["transferegov_disc"] == "TransfereGov — Discricionárias"
        assert rotulos["fns"] == "FNS — Fundo Nacional de Saúde"
        # UF derivada do prefixo do IBGE quando a fonte não a trouxe
        assert {i.uf for i in feed.itens} == {"CE"}


async def _usuario(session, usuario_id):
    from sqlalchemy import select

    from src.models.usuario import Usuario

    return (await session.execute(select(Usuario).where(Usuario.id == usuario_id))).scalar_one()
