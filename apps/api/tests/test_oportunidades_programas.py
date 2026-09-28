"""Oportunidades (§63): programas em que o território pode e deve se inscrever."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.db.session import rls_session
from src.jobs import siconv_diario as job
from src.models.programa import Programa
from src.services import programas as service

HOJE = date(2026, 9, 28)


def _programa(**kw) -> Programa:
    base = {
        "id": uuid.uuid4(),
        "fonte": "siconv",
        "id_externo": "1",
        "nome": "Construção de unidade básica de saúde",
        "orgao_superior": "MINISTERIO DA SAUDE",
        "situacao": "Disponibilizado",
        "ufs": ["CE"],
        "naturezas": ["Administração Pública Municipal"],
        "inicio_proposta": HOJE - timedelta(days=5),
        "fim_proposta": HOJE + timedelta(days=10),
    }
    base.update(kw)
    return Programa(**base)


APUIARES = {"ibge": "2301307", "nome": "Apuiarés", "uf": "CE"}
SAO_PAULO = {"ibge": "3550308", "nome": "São Paulo", "uf": "SP"}


def _avaliar(p: Programa, municipios=None, areas=frozenset(), orgaos=None):
    return service.avaliar(
        p,
        municipios or [APUIARES],
        hoje=HOJE,
        areas=set(areas),
        orgaos_conhecidos=orgaos or {},
    )


# ------------------------------------------------------------- PODE?


def test_uf_nao_habilitada_nao_pode():
    assert _avaliar(_programa(ufs=["SP"])) is None


def test_so_os_municipios_da_uf_habilitada_aparecem():
    av = _avaliar(_programa(ufs=["CE"]), municipios=[APUIARES, SAO_PAULO])
    assert av is not None
    assert [m["ibge"] for m in av.municipios] == ["2301307"]


def test_sem_uf_informada_vale_para_todos():
    av = _avaliar(_programa(ufs=None), municipios=[APUIARES, SAO_PAULO])
    assert av is not None and len(av.municipios) == 2


def test_natureza_municipal_ou_consorcio():
    assert service.aceita_municipio(["Administração Pública Municipal"])
    assert service.aceita_municipio(["Consórcio Público"])
    assert service.aceita_municipio(None)  # a fonte não restringiu
    assert not service.aceita_municipio(["Organização da Sociedade Civil"])


def test_janela_encerrada_ou_programa_inativo_fica_de_fora():
    fechado = _programa(fim_proposta=HOJE - timedelta(days=1))
    assert _avaliar(fechado) is None
    assert _avaliar(_programa(situacao="Inativo")) is None


def test_janela_que_abre_em_breve_entra_como_em_breve():
    p = _programa(inicio_proposta=HOJE + timedelta(days=7), fim_proposta=HOJE + timedelta(days=40))
    av = _avaliar(p)
    assert av is not None
    assert av.janelas[0].status == "em_breve"
    assert av.prazo_final is None  # ainda não dá para inscrever


def test_janela_de_emenda_e_beneficiario_sao_portas_distintas():
    p = _programa(
        inicio_proposta=None,
        fim_proposta=None,
        inicio_emenda=HOJE - timedelta(days=1),
        fim_emenda=HOJE + timedelta(days=20),
    )
    av = _avaliar(p)
    assert av is not None and [j.tipo for j in av.janelas] == ["emenda"]


# ------------------------------------------------------------- DEVE?


def test_historico_do_municipio_recomenda():
    av = _avaliar(_programa(municipios_historico=["2301307"]))
    assert av.recomendado
    assert av.municipios[0]["historico"] is True
    assert any(m.chave == "historico" for m in av.motivos)


def test_area_do_perfil_recomenda():
    av = _avaliar(_programa(), areas={"saude"})
    assert av.recomendado
    assert "saude" in av.categorias


def test_orgao_conhecido_e_contexto_nao_recomendacao():
    """Quase todo município já tratou com os grandes ministérios: contar isso
    marcaria tudo como recomendado."""
    av = _avaliar(_programa(nome="Programa genérico"), orgaos={"ministerio da saude": {"2301307"}})
    assert any(m.chave == "orgao" for m in av.motivos)
    assert not av.recomendado


# ------------------------------------------------------------- carga


def test_sql_agrega_por_programa_e_retem_so_janelas_recentes():
    cols = [
        "id_programa",
        "nome_programa",
        "uf_programa",
        "natureza_juridica_programa",
        "dt_prog_ini_receb_prop",
        "dt_prog_fim_receb_prop",
        "sit_programa",
    ]
    sql = job.sql_upsert_programas(cols)
    assert "GROUP BY btrim(pr.id_programa)" in sql
    assert "ON CONFLICT (fonte, id_externo)" in sql
    assert f"current_date - {job.JANELA_RETENCAO_DIAS}" in sql
    # sem o arquivo de histórico, o que já se sabia é preservado
    assert "coalesce(EXCLUDED.municipios_historico" in sql


def test_sql_historico_recortado_pelo_territorio():
    sql = job.sql_upsert_programas(
        ["id_programa"],
        historico=(["id_programa", "id_proposta"], ["id_proposta", "cod_munic_ibge"]),
        ibges=["2301307"],
    )
    assert "stg_programa_proposta" in sql and "'2301307'" in sql


def test_data_flex_aceita_hora_grudada():
    assert "left(" in job.data_flex("x") and "DD/MM/YYYY" in job.data_flex("x")


# ------------------------------------------------------------- ponta a ponta


async def _seed_programa(**kw) -> None:
    owner = create_async_engine(settings.database_migrator_url, poolclass=NullPool)
    valores = {
        "id_externo": "900",
        "nome": "Aquisição de equipamentos para UBS",
        "ufs": ["CE"],
        "naturezas": ["Administração Pública Municipal"],
        "ini": date.today() - timedelta(days=3),
        "fim": date.today() + timedelta(days=9),
        "historico": None,
        **kw,
    }
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO programas (fonte, id_externo, nome, orgao_superior, situacao, "
                "ufs, naturezas, inicio_proposta, fim_proposta, municipios_historico, "
                "cache_atualizado_em) VALUES ('siconv', :id_externo, :nome, "
                "'MINISTERIO DA SAUDE', 'Disponibilizado', :ufs, :naturezas, :ini, :fim, "
                ":historico, now())"
            ),
            valores,
        )
    await owner.dispose()


async def test_listar_recorta_pelo_territorio_selecionado(seed_user, seed_municipio):
    uid = await seed_user("op@op.com")
    await seed_municipio(uid, "2301307")  # Apuiarés/CE
    await seed_municipio(uid, "3550308")  # São Paulo/SP
    await _seed_programa(id_externo="900", historico=["2301307"])
    await _seed_programa(id_externo="901", nome="Programa só para SP", ufs=["SP"])
    await _seed_programa(
        id_externo="902", nome="Só OSC", naturezas=["Organização da Sociedade Civil"]
    )

    async with rls_session(uid) as s:
        tudo = await service.listar(s, uid)
        so_ce = await service.listar(s, uid, municipio=["2301307"])
        com_osc = await service.listar(s, uid, incluir_outras_naturezas=True)

    assert tudo["catalogo"]["total"] == 3
    assert {p["nome"] for p in tudo["programas"]} == {
        "Aquisição de equipamentos para UBS",
        "Programa só para SP",
    }
    assert [p["nome"] for p in so_ce["programas"]] == ["Aquisição de equipamentos para UBS"]
    assert so_ce["recomendados"] == 1 and so_ce["encerrando"] == 1
    assert len(com_osc["programas"]) == 3


async def test_sem_territorio_devolve_vazio(seed_user):
    uid = await seed_user("vazio@op.com")
    await _seed_programa()
    async with rls_session(uid) as s:
        r = await service.listar(s, uid)
    assert r["programas"] == [] and r["catalogo"]["total"] == 1


# ------------------------------------------------------------- carga real


_PROGRAMA_CSV = (
    "ID_PROGRAMA;COD_PROGRAMA;NOME_PROGRAMA;SIT_PROGRAMA;DESC_ORGAO_SUP_PROGRAMA;"
    "ANO_DISPONIBILIZACAO;DT_PROG_INI_RECEB_PROP;DT_PROG_FIM_RECEB_PROP;"
    "DT_PROG_INI_EMENDA_PAR;DT_PROG_FIM_EMENDA_PAR;MODALIDADE_PROGRAMA;"
    "NATUREZA_JURIDICA_PROGRAMA;UF_PROGRAMA\n"
    # o MESMO programa repetido por UF e por natureza — a carga agrega
    "77;3600020260001;APOIO A UBS;Disponibilizado;MINISTERIO DA SAUDE;2026;"
    "01/09/2026;31/12/2099 23:59:59;;;CONVENIO;Administração Pública Municipal;CE\n"
    "77;3600020260001;APOIO A UBS;Disponibilizado;MINISTERIO DA SAUDE;2026;"
    "01/09/2026;31/12/2099 23:59:59;;;CONVENIO;Consórcio Público;SP\n"
    # janela fechada há anos: fica fora da retenção
    "78;3600020150001;ANTIGO;Disponibilizado;MINISTERIO DA SAUDE;2015;"
    "01/01/2015;31/01/2015;;;CONVENIO;Administração Pública Municipal;CE\n"
)
_PROGRAMA_PROPOSTA_CSV = "ID_PROGRAMA;ID_PROPOSTA\n77;501\n77;502\n"
_PROPOSTA_MIN_CSV = (
    "ID_PROPOSTA;COD_MUNIC_IBGE;NR_PROPOSTA;ANO_PROP\n"
    "501;2301307;000001/2024;2024\n"
    "502;3550308;000002/2024;2024\n"
)


async def test_carga_do_pacote_agrega_e_marca_historico(tmp_path, seed_user, seed_municipio):
    from src.db.session import engine

    uid = await seed_user("carga@op.com")
    await seed_municipio(uid, "2301307")  # só Apuiarés é território monitorado
    arquivos = {}
    for nome, corpo in (
        ("programa", _PROGRAMA_CSV),
        ("programa_proposta", _PROGRAMA_PROPOSTA_CSV),
        ("proposta", _PROPOSTA_MIN_CSV),
    ):
        caminho = tmp_path / f"{nome}.csv"
        caminho.write_text(corpo, encoding="utf-8-sig")
        arquivos[nome] = caminho

    async with engine.begin() as conn:
        gravadas = await job.aplicar_carga(conn, arquivos)
    assert gravadas["programas"] == 1

    owner = create_async_engine(settings.database_migrator_url, poolclass=NullPool)
    async with owner.begin() as conn:
        linha = (
            (
                await conn.execute(
                    text(
                        "SELECT codigo, ufs, naturezas, fim_proposta, municipios_historico "
                        "FROM programas WHERE id_externo = '77'"
                    )
                )
            )
            .mappings()
            .one()
        )
    await owner.dispose()
    assert linha["codigo"] == "3600020260001"
    assert sorted(linha["ufs"]) == ["CE", "SP"]
    assert len(linha["naturezas"]) == 2
    assert linha["fim_proposta"] == date(2099, 12, 31)  # hora grudada não derruba a data
    # histórico recortado pelo TERRITÓRIO: São Paulo propôs, mas não é monitorado
    assert linha["municipios_historico"] == ["2301307"]
