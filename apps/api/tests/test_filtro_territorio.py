"""Filtro de território do painel — ver só ALGUNS dos municípios do perfil.

O usuário escolhe N municípios no onboarding e, na tela, recorta quais deles
quer olhar agora. O recorte atravessa os eixos (captação, recebidos, perfil) e
NUNCA amplia visibilidade: pedir um município fora do território devolve vazio,
porque quem manda continua sendo o RLS.
"""

from __future__ import annotations

from sqlalchemy import text

from src.db.session import rls_session
from src.services import alertas as alertas_service
from src.services import perfil as perfil_service
from src.services import propostas as prop_service
from src.services import repasses as rep_service
from src.services._territorio import ibges

from .conftest import _owner_engine


# ── normalização do filtro (pura, sem banco) ────────────────────────────────
def test_ibges_normaliza_um_varios_ou_nenhum() -> None:
    assert ibges(None) == []
    assert ibges("") == []
    assert ibges("  ") == []
    assert ibges("3550308") == ["3550308"]
    assert ibges(["3550308", "2311801"]) == ["3550308", "2311801"]
    # dedup preservando a ordem de escolha, e sem entradas vazias
    assert ibges(["3550308", "", "3550308", " 2311801 "]) == ["3550308", "2311801"]


async def _seed_proposta(id_externo: str, ibge: str, *, nome: str, uf: str) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                "municipio_nome, uf, situacao, cache_atualizado_em) "
                "VALUES ('transferegov_ff',:e,:t,:ibge,:nome,:uf,'Em análise', now())"
            ),
            {"e": id_externo, "t": f"Proposta {id_externo}", "ibge": ibge, "nome": nome, "uf": uf},
        )


async def _territorio(seed_user, seed_municipio, email: str):
    """Usuário com três municípios monitorados + uma proposta em cada."""
    u = await seed_user(email)
    for ibge in ("3550308", "2311801", "3304557"):
        await seed_municipio(u, ibge)
    await _seed_proposta("SP1", "3550308", nome="São Paulo", uf="SP")
    await _seed_proposta("CE1", "2311801", nome="Russas", uf="CE")
    await _seed_proposta("RJ1", "3304557", nome="Rio de Janeiro", uf="RJ")
    return u


# ── captação ────────────────────────────────────────────────────────────────
async def test_listar_aceita_subconjunto_do_territorio(seed_user, seed_municipio) -> None:
    u = await _territorio(seed_user, seed_municipio, "recorte@x.com")

    async with rls_session(u) as s:
        todos = await prop_service.listar(s)
        assert {p.id_externo for p in todos} == {"SP1", "CE1", "RJ1"}

        # dois dos três — é o caso do painel com vários municípios marcados
        dois = await prop_service.listar(s, municipio=["3550308", "2311801"])
        assert {p.id_externo for p in dois} == {"SP1", "CE1"}

        # um só, como string (contrato antigo) e como lista de um item
        assert [p.id_externo for p in await prop_service.listar(s, municipio="2311801")] == ["CE1"]
        assert [p.id_externo for p in await prop_service.listar(s, municipio=["2311801"])] == [
            "CE1"
        ]

        # lista vazia = sem recorte (todo o território), nunca "nenhum município"
        assert len(await prop_service.listar(s, municipio=[])) == 3


async def test_recorte_nao_amplia_visibilidade(seed_user, seed_municipio) -> None:
    """Município fora do território não vaza nem sendo pedido explicitamente."""
    u = await _territorio(seed_user, seed_municipio, "limite@x.com")
    outro = await seed_user("vizinho@x.com")
    await seed_municipio(outro, "2304400")
    await _seed_proposta("CE9", "2304400", nome="Fortaleza", uf="CE")

    async with rls_session(u) as s:
        assert await prop_service.listar(s, municipio=["2304400"]) == []
        misto = await prop_service.listar(s, municipio=["3550308", "2304400"])
        assert {p.id_externo for p in misto} == {"SP1"}


async def test_facetas_seguem_o_recorte_sem_fechar_o_proprio_dropdown(
    seed_user, seed_municipio
) -> None:
    u = await _territorio(seed_user, seed_municipio, "facetas-recorte@x.com")

    async with rls_session(u) as s:
        facetas = await prop_service.facetas(s, municipio=["3550308", "2311801"])

    # a dimensão município ignora o próprio filtro: o dropdown continua
    # oferecendo todo o território (senão não daria para trocar de recorte)
    assert {o["valor"] for o in facetas["municipio"]} == {"3550308", "2311801", "3304557"}
    # as demais dimensões respeitam o recorte (o Rio ficou de fora)
    assert {o["valor"] for o in facetas["uf"]} == {"SP", "CE"}


# ── recebidos ───────────────────────────────────────────────────────────────
async def test_repasses_aceitam_subconjunto(seed_user, seed_municipio, seed_repasse) -> None:
    u = await seed_user("repasse-recorte@x.com")
    for ibge in ("3550308", "2311801", "3304557"):
        await seed_municipio(u, ibge)
    await seed_repasse("fns", "r-sp", "3550308", valor="100")
    await seed_repasse("fns", "r-ce", "2311801", valor="30")
    await seed_repasse("fns", "r-rj", "3304557", valor="7")

    async with rls_session(u) as s:
        rows = await rep_service.listar(s, municipio=["3550308", "2311801"])
        assert {r.id_externo for r in rows} == {"r-sp", "r-ce"}

        vg = await rep_service.visao_geral(s, municipio=["3550308", "2311801"])
        assert vg.movimentacoes == 2
        assert vg.total_pago == 130


# ── perfil (Meu painel) ─────────────────────────────────────────────────────
async def test_visao_geral_e_feed_do_perfil_seguem_o_recorte(
    seed_user, seed_municipio, seed_repasse
) -> None:
    u = await _territorio(seed_user, seed_municipio, "painel-recorte@x.com")
    await seed_repasse("fns", "r-sp", "3550308", valor="100")
    await seed_repasse("fns", "r-ce", "2311801", valor="30")
    usuario = _FakeUser(u)

    async with rls_session(u) as s:
        inteiro = await perfil_service.visao_geral(s, usuario)
        recorte = await perfil_service.visao_geral(s, usuario, municipios_filtro=["3550308"])
        feed = await perfil_service.novidades(s, usuario, municipios_filtro=["3550308"])

    assert {d.chave: d.total for d in inteiro.dimensoes}["captacao"] == 3
    dims = {d.chave: d.total for d in recorte.dimensoes}
    assert dims["captacao"] == 1  # só São Paulo
    assert dims["recebidos"] == 1
    # o cabeçalho do painel mostra o território que está sendo visto, não todo ele
    assert {m.ibge for m in recorte.municipios} == {"3550308"}
    assert {i.municipio_ibge for i in feed.itens} == {"3550308"}


# ── alertas ─────────────────────────────────────────────────────────────────
async def test_alertas_seguem_o_recorte_por_payload_ou_proposta(seed_user, seed_municipio) -> None:
    """O município do alerta vem do payload; nos de mudança, da proposta ligada."""
    u = await _territorio(seed_user, seed_municipio, "alerta-recorte@x.com")

    async with rls_session(u) as s:
        proposta_sp = (await prop_service.listar(s, municipio="3550308"))[0]

    async with _owner_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(u)})
        await conn.execute(
            text(
                # `lido` é NOT NULL sem default no banco (o default é do ORM):
                # INSERT cru precisa dizer o valor. Os dois tipos aqui são
                # LEGADOS de propósito — o de-para de leitura tem que continuar
                # servindo o alerta que já está gravado (§56).
                "INSERT INTO alertas (usuario_id, proposta_id, tipo, payload, lido) VALUES "
                "(:u, NULL, 'oportunidade', '{\"municipio_ibge\":\"2311801\"}'::jsonb, false), "
                "(:u, :p, 'status', '{\"mudou\":{}}'::jsonb, false)"
            ),
            {"u": u, "p": proposta_sp.id},
        )

    async with rls_session(u) as s:
        assert len(await alertas_service.listar(s, u)) == 2
        # payload com o município (alerta de oportunidade)
        so_ce = await alertas_service.listar(s, u, municipio=["2311801"])
        assert [a.tipo for a in so_ce] == ["oportunidade"]
        # município resolvido pela proposta ligada (alerta de mudança)
        so_sp = await alertas_service.listar(s, u, municipio=["3550308"])
        assert [a.tipo for a in so_sp] == ["status"]
        assert await alertas_service.listar(s, u, municipio=["3304557"]) == []


class _FakeUser:
    """Stand-in do modelo Usuario (só os atributos que o serviço lê)."""

    def __init__(self, uid) -> None:
        self.id = uid
        self.papel = "executivo"
        self.nome = None
