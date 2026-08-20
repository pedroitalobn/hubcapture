"""Carga das PROPOSTAS do pacote SIconv — todas as discricionárias e legais.

O pacote nacional é o único caminho para "quero TODAS as propostas do meu
município": a fonte não publica rota de consulta por município para as
discricionárias/legais. O que se protege aqui é o que quebra silenciosamente
numa carga — recorte de território, identidade da linha e RLS entregando zero
em vez de erro.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text as sql_text

from src.connectors import siconv_downloads
from src.db.session import engine
from src.jobs import siconv_diario as job

COLS = [
    "id_proposta",
    "uf_proponente",
    "munic_proponente",
    "cod_munic_ibge",
    "nr_proposta",
    "dia_prop",
    "mes_prop",
    "ano_prop",
    "objeto_proposta",
    "sit_proposta",
    "modalidade",
    "desc_orgao_sup",
    "vl_global_prop",
    "vl_repasse_prop",
    "vl_contrapartida_prop",
    "dia_fim_vigencia_proposta",
]

# Duas propostas de Monte Carlo (4211272) e uma de outro município, para o
# recorte de território ter o que descartar.
_PROPOSTA_CSV = (
    "ID_PROPOSTA;UF_PROPONENTE;MUNIC_PROPONENTE;COD_MUNIC_IBGE;NR_PROPOSTA;"
    "DIA_PROP;MES_PROP;ANO_PROP;OBJETO_PROPOSTA;SIT_PROPOSTA;MODALIDADE;"
    "DESC_ORGAO_SUP;VL_GLOBAL_PROP;VL_REPASSE_PROP;VL_CONTRAPARTIDA_PROP;"
    "DIA_FIM_VIGENCIA_PROPOSTA;NM_PROPONENTE;NATUREZA_JURIDICA\n"
    "901;SC;MONTE CARLO;4211272;014275/2024;26;03;2024;Construção de UBS;"
    "Proposta/Plano de Trabalho Aprovados;CONVENIO;Ministério da Saúde;"
    "1.500.000,00;1.450.000,00;50.000,00;31/12/2026;MUNICIPIO DE MONTE CARLO;"
    "Administração Pública Municipal\n"
    "902;SC;MONTE CARLO;4211272;030011/2026;01;02;2026;Pavimentação de vias;"
    "Proposta/Plano de Trabalho em Análise;CONTRATO DE REPASSE;Ministério das Cidades;"
    "800000;760000;40000;;MUNICIPIO DE MONTE CARLO;Administração Pública Municipal\n"
    "903;SP;SAO PAULO;3550308;000777/2025;10;10;2025;Escola;Em análise;CONVENIO;"
    "MEC;5000;5000;0;;MUNICIPIO DE SAO PAULO;Administração Pública Municipal\n"
    # sem IBGE: não há como dizer de que território é — fica fora
    "904;;;;000888/2025;10;10;2025;Sem municipio;Em análise;CONVENIO;MEC;10;10;0;;;\n"
)


# --------------------------------------------------------------------------
# SQL puro (sem banco)
# --------------------------------------------------------------------------


def test_fonte_e_a_mesma_do_connector_que_le_o_arquivo():
    """Fonte própria faria a MESMA proposta aparecer duas vezes no painel: a
    chave do cache é (fonte, id_externo) e os dois caminhos leem o mesmo CSV."""
    assert job.FONTE_PROPOSTA == "transferegov_disc"


def test_identidade_e_o_id_publicado_pela_fonte():
    sql = job.sql_upsert_propostas(COLS, ibges=None)
    assert "DISTINCT ON (p.id_proposta)" in sql
    assert "left(p.id_proposta, 255)" in sql
    # RETURNING leria sob a policy de SELECT e reportaria zero com a tabela
    # cheia — o mesmo tropeço da §41.
    assert "RETURNING" not in sql.upper()


def test_recorte_de_territorio_entra_na_varredura():
    """Carregar o país e descartar depois custaria a carga inteira em disco."""
    sql = job.sql_upsert_propostas(COLS, ibges=["4211272", "3550308"])
    assert "IN ('4211272', '3550308')" in sql

    # território vazio não pode virar "carrega tudo"
    assert " AND false" in job.sql_upsert_propostas(COLS, ibges=[])

    # nacional é explícito: sem filtro de município
    assert "IN ('" not in job.sql_upsert_propostas(COLS, ibges=None)


def test_data_de_criacao_vem_dos_tres_componentes():
    """DIA_PROP+MES_PROP+ANO_PROP são as variáveis oficiais (§35b); coluna única
    de data é retaguarda, nunca a preferência."""
    expr = job.data_componentes("p.dia_prop", "p.mes_prop", "p.ano_prop", "p.dia_proposta")
    assert "p.ano_prop" in expr and "p.dia_prop" in expr and "p.mes_prop" in expr
    assert "to_date" in expr and "make_date" not in expr


def test_coluna_renomeada_pela_fonte_nao_derruba_a_carga():
    sql = job.sql_upsert_propostas(["id_proposta", "cod_munic_ibge"], ibges=None)
    assert "NULL::text" in sql and "ON CONFLICT" in sql


def test_execucao_do_painel_nao_e_sobrescrita_pelo_csv():
    """O painel da Visão Geral traz empenhado/pago/saldo, que o CSV não tem: o
    pacote COMPLETA o bloco de execução em vez de apagá-lo."""
    sql = job.sql_upsert_propostas(COLS, ibges=None)
    assert "coalesce(propostas.execucao, '{}'::jsonb) || EXCLUDED.execucao" in sql


def test_upsert_desfaz_zeragem_anterior():
    """A fonte ainda publica a proposta: uma zeragem (§41) não pode mantê-la
    invisível para sempre."""
    assert "excluido_em     = NULL" in job.sql_upsert_propostas(COLS, ibges=None)


# --------------------------------------------------------------------------
# integração — o SQL roda de verdade contra o Postgres
# --------------------------------------------------------------------------


async def _carregar(tmp_path: Path) -> dict[str, int]:
    caminho = tmp_path / "proposta.csv"
    caminho.write_text(_PROPOSTA_CSV, encoding="utf-8-sig")
    async with engine.begin() as conn:
        return await job.aplicar_carga(conn, {"proposta": caminho})


async def _propostas() -> list[dict]:
    from tests.conftest import _owner_engine

    async with _owner_engine.begin() as conn:
        # `propostas` está sob FORCE RLS: nem o owner escapa da policy por
        # município. Sem a bandeira o teste veria zero e leria como "não gravou".
        await conn.execute(sql_text("SELECT set_config('app.plataforma', 'on', true)"))
        linhas = (
            await conn.execute(
                sql_text(
                    "SELECT id_externo, numero_proposta, objeto, orgao_superior, modalidade, "
                    "municipio_ibge, municipio_nome, uf, valor_total, contrapartida, situacao, "
                    "prazos, data_proposta, execucao, dados_fonte, proveniencia, excluido_em "
                    "FROM propostas WHERE fonte = 'transferegov_disc' ORDER BY id_externo"
                )
            )
        ).mappings()
        return [dict(r) for r in linhas]


async def test_carga_recorta_pelo_territorio_monitorado(tmp_path, seed_user, seed_municipio):
    """O padrão é o território: o arquivo é nacional e o cache só é lido por
    município — carregar o país inteiro é decisão de operação, não default."""
    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")

    gravadas = await _carregar(tmp_path)
    assert gravadas["propostas"] == 2

    linhas = await _propostas()
    assert [linha["id_externo"] for linha in linhas] == ["901", "902"]
    assert all(linha["municipio_ibge"] == "4211272" for linha in linhas)


async def test_campos_da_proposta_chegam_completos(tmp_path, seed_user, seed_municipio):
    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await _carregar(tmp_path)

    ubs = (await _propostas())[0]
    assert ubs["numero_proposta"] == "014275/2024"  # a referência que o gestor digita
    assert ubs["objeto"] == "Construção de UBS"
    assert ubs["orgao_superior"] == "Ministério da Saúde"
    assert ubs["modalidade"] == "CONVENIO"
    assert ubs["municipio_nome"] == "MONTE CARLO" and ubs["uf"] == "SC"
    # `1.500.000,00` é BR: ponto de milhar fora, vírgula vira decimal
    assert ubs["valor_total"] == Decimal("1500000.00")
    assert ubs["contrapartida"] == Decimal("50000.00")
    assert ubs["situacao"].startswith("Proposta/Plano de Trabalho")
    # data de CRIAÇÃO remontada dos três componentes (§35b)
    assert ubs["data_proposta"] == date(2024, 3, 26)
    assert ubs["execucao"]["valor_global"] == 1500000.00
    assert ubs["execucao"]["ano"] == 2024
    # fim de vigência vira prazo estruturado (alimenta /proposals/deadlines)
    assert ubs["prazos"] == [{"tipo": "fim de vigência", "data_limite": "2026-12-31"}]
    # registro-fonte no MESMO formato do connector: `plano_acao.csv` = linha bruta
    assert ubs["dados_fonte"]["plano_acao"]["csv"]["ano_prop"] == "2024"
    assert ubs["proveniencia"]["numero_proposta"] == "siconv:proposta.NR_PROPOSTA"


async def test_proposta_sem_ibge_fica_fora(tmp_path, seed_user, seed_municipio):
    """Sem município não há território: entrar carimbaria a proposta no
    território errado ou a deixaria invisível para todos."""
    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await _carregar(tmp_path)
    assert "904" not in [linha["id_externo"] for linha in await _propostas()]


async def test_carga_e_idempotente(tmp_path, seed_user, seed_municipio):
    """Job diário: rodar de novo atualiza a linha, não cria outra."""
    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await _carregar(tmp_path)
    assert (await _carregar(tmp_path))["propostas"] == 2
    assert len(await _propostas()) == 2


async def test_recoleta_ressuscita_proposta_zerada(tmp_path, seed_user, seed_municipio):
    """A zeragem (§41) é soft delete; a fonte ainda publica a proposta, então a
    carga seguinte a traz de volta em vez de deixá-la invisível para sempre."""
    from tests.conftest import _owner_engine

    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await _carregar(tmp_path)

    async with _owner_engine.begin() as conn:
        await conn.execute(sql_text("UPDATE propostas SET excluido_em = now()"))

    await _carregar(tmp_path)
    assert all(linha["excluido_em"] is None for linha in await _propostas())


async def test_sem_territorio_a_carga_nao_grava_o_pais_inteiro(tmp_path):
    """Instalação nova (nenhum município monitorado): melhor zero e dito no log
    que o país inteiro "por via das dúvidas"."""
    gravadas = await _carregar(tmp_path)
    assert gravadas["propostas"] == 0
    assert await _propostas() == []


async def test_escopo_nacional_carrega_todo_mundo(tmp_path, monkeypatch):
    from src.services import config as config_service

    async def _resolver(chave: str):
        return "nacional" if chave == "siconv_propostas_escopo" else None

    monkeypatch.setattr(config_service, "resolver", _resolver)
    assert await job.escopo_propostas() == job.ESCOPO_NACIONAL

    gravadas = await _carregar(tmp_path)
    assert gravadas["propostas"] == 3  # as 3 com IBGE, sem nenhum território
    assert {linha["municipio_ibge"] for linha in await _propostas()} == {"4211272", "3550308"}


async def test_a_carga_le_o_territorio_de_todos_os_usuarios(tmp_path, seed_user, seed_municipio):
    """`municipios_interesse` é por-tenant sob FORCE RLS: sem a bandeira de
    plataforma o job leria zero e entregaria uma carga vazia em silêncio."""
    a = await seed_user("a@hub.gov.br")
    b = await seed_user("b@hub.gov.br")
    await seed_municipio(a, "4211272")
    await seed_municipio(b, "3550308")

    async with engine.begin() as conn:
        await conn.execute(sql_text("SELECT set_config('app.plataforma', 'on', true)"))
        assert await job.ibges_do_territorio(conn) == ["3550308", "4211272"]

    assert (await _carregar(tmp_path))["propostas"] == 3


# --------------------------------------------------------------------------
# catálogo de arquivos do pacote
# --------------------------------------------------------------------------


def test_catalogo_cobre_o_pacote_e_marca_o_que_tem_destino():
    catalogo = siconv_downloads.ARQUIVOS
    # o que a carga alimenta hoje
    assert {"proposta", "emenda", "convenio", "empenho"} <= set(catalogo)
    assert catalogo["proposta"].carrega
    # mapeado para conferência, mas fora da carga (baixar sem destino é desperdício)
    assert not catalogo["programa"].carrega
    assert not catalogo["historico_situacao"].carrega


async def test_candidatos_respeitam_o_override_do_painel(monkeypatch):
    from src.services import config as config_service

    async def _resolver(chave: str):
        return "SICONV_PROPOSTA_2026.zip" if chave == "siconv_proposta_arquivo" else None

    monkeypatch.setattr(config_service, "resolver", _resolver)
    assert await siconv_downloads.candidatos("proposta") == ("SICONV_PROPOSTA_2026.zip",)


async def test_tabela_fora_do_catalogo_e_recusada_com_nome():
    import pytest

    with pytest.raises(siconv_downloads.DownloadError, match="tabela desconhecida"):
        await siconv_downloads.candidatos("tabela_que_nao_existe")


async def test_executar_ignora_tabela_fora_do_catalogo(monkeypatch, tmp_path):
    """Recorte inválido degrada o lote; não derruba a carga."""
    baixadas: list[str] = []

    async def _baixar(tabela, destino_dir, base=None):
        baixadas.append(tabela)
        caminho = tmp_path / f"{tabela}.csv"
        caminho.write_text(_PROPOSTA_CSV, encoding="utf-8-sig")
        return caminho

    monkeypatch.setattr(siconv_downloads, "baixar_csv", _baixar)
    resultado = await job.executar(dir_trabalho=str(tmp_path), tabelas=("proposta", "inexistente"))
    assert baixadas == ["proposta"]
    assert resultado["status"] == "ok"


def test_ids_sinteticos_nao_colidem_entre_municipios():
    """Retaguarda do connector quando a linha não tem ID_PROPOSTA: o hash é
    escopado no município — senão a proposta "1" de um território sobrescreve a
    do outro (§51)."""
    from src.connectors import _identidade

    linha = {"OBJETO": "UBS", "VALOR": "10"}
    assert _identidade.hash_conteudo(linha, "4211272") != _identidade.hash_conteudo(
        linha, "3550308"
    )
    # determinístico: a mesma linha rende sempre o mesmo id (atualiza, não duplica)
    assert _identidade.hash_conteudo(linha, "4211272") == _identidade.hash_conteudo(
        linha, "4211272"
    )


def test_uuid_nao_vaza_para_o_id_externo():
    """Sanidade: o id da linha é o da FONTE, nunca um uuid gerado aqui."""
    sql = job.sql_upsert_propostas(COLS, ibges=None)
    assert sql.index("gen_random_uuid()") < sql.index("left(p.id_proposta")
    assert str(uuid.uuid4()) not in sql


# --------------------------------------------------------------------------
# o painel lê ESTA tabela — a carga não é um depósito paralelo
# --------------------------------------------------------------------------


async def test_o_painel_do_gestor_ve_as_propostas_carregadas(tmp_path, seed_user, seed_municipio):
    """A carga grava na tabela canônica `propostas`, que é a MESMA que a
    Captação lê — não num depósito paralelo. Este teste percorre o caminho real:
    carga global sem tenant → leitura sob a sessão RLS do usuário.
    """
    from src.db.session import rls_session
    from src.services import propostas as prop_service

    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    await _carregar(tmp_path)

    async with rls_session(uid) as s:
        vistas = await prop_service.listar(s)

    assert {p.numero_proposta for p in vistas} == {"014275/2024", "030011/2026"}
    # a ordem do painel é a data de CRIAÇÃO na fonte (§43): a de 2026 na frente
    assert vistas[0].numero_proposta == "030011/2026"
    # e o filtro de safra enxerga o ano da proposta, não o da coleta
    async with rls_session(uid) as s:
        de_2024 = await prop_service.listar(s, ano=2024)
    assert [p.numero_proposta for p in de_2024] == ["014275/2024"]


async def test_proposta_de_outro_municipio_nao_vaza_para_o_painel(
    tmp_path, seed_user, seed_municipio, monkeypatch
):
    """Carga nacional não pode furar o RLS: o gestor continua vendo só o seu
    território, mesmo com o país inteiro no cache."""
    from src.db.session import rls_session
    from src.services import config as config_service
    from src.services import propostas as prop_service

    async def _resolver(chave: str):
        return "nacional" if chave == "siconv_propostas_escopo" else None

    monkeypatch.setattr(config_service, "resolver", _resolver)

    uid = await seed_user("gestor@hub.gov.br")
    await seed_municipio(uid, "4211272")
    assert (await _carregar(tmp_path))["propostas"] == 3  # 4211272 e 3550308

    async with rls_session(uid) as s:
        vistas = await prop_service.listar(s)
    assert {p.municipio_ibge for p in vistas} == {"4211272"}
