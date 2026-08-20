"""Recorte de FONTE — o filtro global do trilho lateral (irmão do de território).

O usuário escolhe as fontes no onboarding; no painel ele decide QUAIS delas
quer ver naquele momento. O recorte é global (vale para todas as lentes), é um
SUBCONJUNTO (nunca amplia) e fala o vocabulário do usuário — GRUPO
("transferegov", "fns"), não connector id.
"""

from __future__ import annotations

from src.db.session import rls_session
from src.services import fontes as fontes_service
from src.services import propostas as propostas_service

# ── Normalização: grupo → connector ids ─────────────────────────────────────


def test_recorte_expande_grupo_em_connectors() -> None:
    assert fontes_service.recorte("transferegov") == list(fontes_service.TRANSFEREGOV)
    assert fontes_service.recorte(["fns"]) == ["fns"]
    # grupo e connector id convivem (o painel manda grupo; perfis antigos, id)
    assert fontes_service.recorte(["fns", "transferegov_ff"]) == ["fns", "transferegov_ff"]


def test_recorte_vazio_quando_nao_ha_escolha() -> None:
    assert fontes_service.recorte(None) == []
    assert fontes_service.recorte([]) == []
    assert fontes_service.recorte("") == []


def test_recorte_descarta_fonte_fora_de_operacao() -> None:
    """Fonte fora do corte da v1 não existe — não é escolha inválida do usuário."""
    assert fontes_service.recorte(["fpm", "emendas"]) == []
    assert fontes_service.recorte(["transferegov", "fpm"]) == list(fontes_service.TRANSFEREGOV)


# ── Aplicação: o que o recorte pode e o que NÃO pode zerar ──────────────────


async def test_listagem_recortada_por_grupo(seed_user, seed_municipio, seed_proposta) -> None:
    uid = await seed_user("rf@x.com")
    await seed_municipio(uid, "2301109")
    await seed_proposta("transferegov_ff", "P-FF", "2301109")
    await seed_proposta("serpro", "P-SERPRO", "2301109")
    await seed_proposta("fns", "P-FNS", "2301109")

    async with rls_session(uid) as s:
        # sem recorte: tudo do território
        assert len(await propostas_service.listar(s, municipio="2301109")) == 3
        # grupo TransfereGov cobre os cinco connectors dele (ff + serpro aqui)
        rows = await propostas_service.listar(s, municipio="2301109", fonte="transferegov")
        assert sorted(p.id_externo for p in rows) == ["P-FF", "P-SERPRO"]
        # um connector id continua valendo (perfil antigo, chamada direta)
        rows = await propostas_service.listar(s, municipio="2301109", fonte=["transferegov_ff"])
        assert [p.id_externo for p in rows] == ["P-FF"]
        # multi-seleção: a união dos grupos
        rows = await propostas_service.listar(s, municipio="2301109", fonte=["transferegov", "fns"])
        assert len(rows) == 3


async def test_escolha_que_nao_casa_nada_nao_devolve_tudo(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Pedido explícito que expande para nada é vazio, nunca 'sem recorte'."""
    uid = await seed_user("rf2@x.com")
    await seed_municipio(uid, "2301109")
    await seed_proposta("transferegov_ff", "P1", "2301109")

    async with rls_session(uid) as s:
        assert await propostas_service.listar(s, municipio="2301109", fonte=["fpm"]) == []


async def test_recorte_nao_zera_eixo_de_fonte_que_o_seletor_nao_oferece(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """O seletor lista TransfereGov e FNS — escolher um deles não pode apagar
    obras/conformidade, que vêm de connectors fora desse universo."""
    uid = await seed_user("rf3@x.com")
    await seed_municipio(uid, "2301109")
    # `sismob` alimenta OBRAS e está fora do recorte da v1 (não é ofertável)
    await seed_proposta("sismob", "FORA-DO-UNIVERSO", "2301109")
    await seed_proposta("fns", "P-FNS", "2301109")

    async with rls_session(uid) as s:
        rows = await propostas_service.listar(s, municipio="2301109", fonte="transferegov")
        # o FNS saiu (é ofertável e não foi escolhido); o de fora passou intacto
        assert [p.id_externo for p in rows] == ["FORA-DO-UNIVERSO"]


# ── Coleta ao vivo: pedido explícito nunca vira "colete tudo" ───────────────


def test_pedido_de_fonte_desconhecida_nao_cai_no_padrao() -> None:
    """Descartar o nome em silêncio faria a rodada coletar TODAS as fontes —
    o oposto do que se pediu. O nome segue e vira incidente na coleta."""
    from src.services.consulta_avulsa import _fontes_alvo

    assert _fontes_alvo("nao_existe", None, None) == ["nao_existe"]


def test_fonte_conhecida_que_nao_produz_proposta_nao_e_incidente() -> None:
    """FNS produz repasse, não proposta: a captação não tem o que coletar dela
    — resposta honestamente vazia, sem erro inventado."""
    from src.services.consulta_avulsa import _fontes_alvo

    assert _fontes_alvo(["fns"], None, None) == []


def test_grupo_expande_para_os_connectors_de_captacao() -> None:
    from src.services.consulta_avulsa import CAPTACAO_FONTES, _fontes_alvo

    assert _fontes_alvo("transferegov", None, None) == [
        f for f in fontes_service.TRANSFEREGOV if f in CAPTACAO_FONTES
    ]
