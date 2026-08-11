"""Busca do painel: número, município, natureza jurídica e range de valor."""

from __future__ import annotations

from decimal import Decimal

from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion.normalizer import natureza_juridica, normalize
from src.services import propostas as svc


async def _cenario(seed_user, seed_municipio, seed_proposta):
    """Um usuário com dois municípios e quatro propostas variadas."""
    uid = await seed_user("busca@busca.com")
    await seed_municipio(uid, "3550308")
    await seed_municipio(uid, "3304557")
    await seed_proposta(
        "transferegov_ff", "1001", "3550308", "UBS",
        numero_proposta="0012345/2026",
        natureza_juridica="administracao_publica_municipal",
        valor_total="100000.00", municipio_nome="São Paulo", uf="SP",
    )
    await seed_proposta(
        "transferegov_ff", "1002", "3550308", "Escola",
        numero_proposta="0067890/2026",
        natureza_juridica="consorcio_publico",
        valor_total="900000.00", municipio_nome="São Paulo", uf="SP",
    )
    await seed_proposta(
        "fns", "2001", "3304557", "Ambulância",
        numero_proposta="0012399/2026",
        natureza_juridica="organizacao_sociedade_civil",
        valor_total="50000.00", municipio_nome="Rio de Janeiro", uf="RJ",
    )
    await seed_proposta(
        "fns", "2002", "3304557", "Sem valor",
        natureza_juridica="administracao_publica_municipal",
        emenda="4021/2026",
    )
    return uid


async def test_busca_por_numero_casa_numero_id_externo_e_emenda(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)

    async with rls_session(uid) as s:
        # trecho do numero_proposta → pega as duas que começam com 00123
        rows = await svc.listar(s, numero="00123")
        assert {r.id_externo for r in rows} == {"1001", "2001"}

        # o "Nº" que o painel exibe é o id_externo — buscar por ele funciona
        assert {r.id_externo for r in await svc.listar(s, numero="1002")} == {"1002"}

        # emenda também é um "número" que o gestor digita
        assert {r.id_externo for r in await svc.listar(s, numero="4021")} == {"2002"}

        # curinga do usuário é literal, não wildcard SQL
        assert await svc.listar(s, numero="%") == []


async def test_filtro_de_municipio_aceita_varios(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)

    async with rls_session(uid) as s:
        rows = await svc.listar(s, municipios=["3304557"])
        assert {r.id_externo for r in rows} == {"2001", "2002"}

        rows = await svc.listar(s, municipios=["3304557", "3550308"])
        assert len(rows) == 4


async def test_filtro_por_natureza_juridica(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)

    async with rls_session(uid) as s:
        rows = await svc.listar(
            s, naturezas_juridicas=["administracao_publica_municipal"]
        )
        assert {r.id_externo for r in rows} == {"1001", "2002"}

        rows = await svc.listar(
            s, naturezas_juridicas=["consorcio_publico", "organizacao_sociedade_civil"]
        )
        assert {r.id_externo for r in rows} == {"1002", "2001"}


async def test_range_de_valor(seed_user, seed_municipio, seed_proposta) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)

    async with rls_session(uid) as s:
        rows = await svc.listar(s, valor_min=Decimal("60000"))
        assert {r.id_externo for r in rows} == {"1001", "1002"}

        rows = await svc.listar(
            s, valor_min=Decimal("60000"), valor_max=Decimal("200000")
        )
        assert {r.id_externo for r in rows} == {"1001"}

        # proposta sem valor informado fica de fora quando há corte
        rows = await svc.listar(s, valor_max=Decimal("999999999"))
        assert "2002" not in {r.id_externo for r in rows}


async def test_filtros_combinam_e_respeitam_rls(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)
    outro = await seed_user("outro@outro.com")
    await seed_municipio(outro, "2301109")
    await seed_proposta(
        "fns", "9999", "2301109", "De outro tenant",
        numero_proposta="0012300/2026",
        natureza_juridica="administracao_publica_municipal",
        valor_total="100000.00",
    )

    async with rls_session(uid) as s:
        rows = await svc.listar(
            s,
            numero="0012",
            municipios=["3550308"],
            naturezas_juridicas=["administracao_publica_municipal"],
            valor_min=Decimal("1"),
            valor_max=Decimal("500000"),
        )
        assert {r.id_externo for r in rows} == {"1001"}

        # a proposta do outro tenant casaria com o filtro, mas o RLS a esconde
        assert "9999" not in {r.id_externo for r in await svc.listar(s, numero="00123")}


async def test_opcoes_de_filtro_saem_do_cache_visivel(
    seed_user, seed_municipio, seed_proposta
) -> None:
    uid = await _cenario(seed_user, seed_municipio, seed_proposta)

    async with rls_session(uid) as s:
        f = await svc.filtros(s)

    assert f.total == 4
    assert {m.valor for m in f.municipios} == {"3550308", "3304557"}
    assert {m.label for m in f.municipios} == {"São Paulo/SP", "Rio de Janeiro/RJ"}
    assert dict((m.valor, m.total) for m in f.municipios)["3550308"] == 2
    naturezas = {n.valor: n.label for n in f.naturezas_juridicas}
    assert naturezas["consorcio_publico"] == "Consórcio público"
    assert {fo.valor for fo in f.fontes} == {"transferegov_ff", "fns"}
    assert f.valor_min == Decimal("50000.00")
    assert f.valor_max == Decimal("900000.00")


def test_natureza_juridica_normaliza_rotulo_da_fonte() -> None:
    assert (
        natureza_juridica("Administração Pública Municipal")
        == "administracao_publica_municipal"
    )
    assert natureza_juridica("CONSÓRCIO PÚBLICO MUNICIPAL") == "consorcio_publico"
    assert (
        natureza_juridica("Organização da Sociedade Civil")
        == "organizacao_sociedade_civil"
    )
    assert natureza_juridica(None, "", "Fundação Estadual") == (
        "administracao_publica_estadual"
    )
    assert natureza_juridica("Coisa que ninguém mapeou") == "outros"
    # sem informação da fonte não vira 'outros' — fica ausente
    assert natureza_juridica(None) is None


def test_normalize_extrai_natureza_do_beneficiario() -> None:
    canonica = normalize(
        RawRecord(
            source_id="transferegov_ff",
            id_externo="X1",
            municipio_ibge="3550308",
            raw={
                "plano_acao": {"valor_total": "10"},
                "programa": {"nome_programa": "Prog"},
                "beneficiario": {"nome_natureza_juridica": "Prefeitura Municipal"},
            },
        )
    )
    assert canonica.natureza_juridica == "administracao_publica_municipal"
