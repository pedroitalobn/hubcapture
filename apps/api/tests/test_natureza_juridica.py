"""Natureza jurídica: classificação, filtro na listagem e quebra no painel."""

from __future__ import annotations

import pytest

from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion import natureza_juridica as nj
from src.ingestion.normalizer import normalize
from src.services import perfil as perfil_service
from src.services import propostas as propostas_service


@pytest.mark.parametrize(
    "texto",
    [
        "Prefeitura Municipal de Uberaba",
        "MUNICIPIO DE SAO PAULO",
        "Secretaria Municipal de Saúde",
        "Fundo Municipal de Assistência Social",
        "Consórcio Público Intermunicipal de Saúde",
        "Câmara de Vereadores de Contagem",
        "Administração Pública Municipal",
    ],
)
def test_classifica_entes_municipais(texto: str) -> None:
    assert nj.classificar(texto) == nj.ENTES_MUNICIPAIS


@pytest.mark.parametrize(
    "texto",
    [
        "Organização da Sociedade Civil",
        "Associação de Pais e Amigos dos Excepcionais",
        "Secretaria de Estado da Educação",
        "Fundo Estadual de Saúde",
        "Administração Pública Federal",
        "Cooperativa Agropecuária Ltda",
    ],
)
def test_classifica_outros(texto: str) -> None:
    assert nj.classificar(texto) == nj.OUTROS


def test_codigo_concla_vence_o_texto() -> None:
    # 1244 = Município; o código é mais confiável que o nome fantasia.
    assert nj.classificar("Instituto Recomeço", codigo="124-4") == nj.ENTES_MUNICIPAIS
    # 3999 = Associação Privada → não é ente municipal, mesmo com "municipal" no nome.
    assert nj.classificar("Associação Municipalista", codigo="3999") == nj.OUTROS


def test_sem_sinal_usa_padrao_da_fonte() -> None:
    # fundo a fundo repassa ao próprio ente municipal
    assert nj.classificar(fonte="transferegov_ff") == nj.ENTES_MUNICIPAIS
    # fonte sem padrão definido não presume ente municipal
    assert nj.classificar(fonte="transferegov_disc") == nj.OUTROS


def test_normalize_extrai_natureza_do_beneficiario() -> None:
    record = RawRecord(
        source_id="transferegov_ff",
        id_externo="1",
        municipio_ibge="3170206",
        raw={
            "plano_acao": {"situacao": "Nova"},
            "programa": {"nome_programa": "Prog"},
            "beneficiario": {"nome_natureza_juridica": "Administração Pública Municipal"},
        },
    )
    canonica = normalize(record)
    assert canonica.natureza_juridica == nj.ENTES_MUNICIPAIS
    assert canonica.natureza_juridica_descricao == "Administração Pública Municipal"
    assert (canonica.proveniencia or {}).get("natureza_juridica") == "api"


def test_normalize_marca_natureza_inferida_na_proveniencia() -> None:
    record = RawRecord(
        source_id="transferegov_ff",
        id_externo="2",
        municipio_ibge="3170206",
        raw={"plano_acao": {}, "programa": {}, "beneficiario": {}},
    )
    canonica = normalize(record)
    assert canonica.natureza_juridica == nj.ENTES_MUNICIPAIS  # padrão da fonte
    assert canonica.natureza_juridica_descricao is None
    assert (canonica.proveniencia or {}).get("natureza_juridica") == "derivado"


async def test_listar_filtra_por_natureza(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("nj@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "m1", "3550308", natureza_juridica="entes_municipais")
    await seed_proposta("fnde", "o1", "3550308", natureza_juridica="outros")
    await seed_proposta("fnde", "legado", "3550308")  # sem classificação (cache antigo)

    async with rls_session(u) as s:
        todas = await propostas_service.listar(s)
        municipais = await propostas_service.listar(s, natureza_juridica="entes_municipais")
        outros = await propostas_service.listar(s, natureza_juridica="outros")

    assert len(todas) == 3
    assert {p.id_externo for p in municipais} == {"m1"}
    # linha sem classificação entra em 'outros' — as duas lentes cobrem a base toda
    assert {p.id_externo for p in outros} == {"o1", "legado"}


async def test_visao_geral_traz_quebra_por_natureza(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("njp@a.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("transferegov_ff", "m1", "3550308", natureza_juridica="entes_municipais")
    await seed_proposta("transferegov_ff", "m2", "3550308", natureza_juridica="entes_municipais")
    await seed_proposta("fnde", "o1", "3550308", natureza_juridica="outros")

    async with rls_session(u) as s:
        vg = await perfil_service.visao_geral(s, _FakeUser(u))

    captacao = next(d for d in vg.dimensoes if d.chave == "captacao")
    quebras = {q.chave: q for q in captacao.quebras}
    assert quebras["entes_municipais"].total == 2
    assert quebras["outros"].total == 1
    assert quebras["entes_municipais"].rotulo == "Entes municipais"
    assert quebras["outros"].href == "/painel/captacao?natureza=outros"


class _FakeUser:
    def __init__(self, uid) -> None:
        self.id = uid
        self.papel = "executivo"
        self.nome = None
