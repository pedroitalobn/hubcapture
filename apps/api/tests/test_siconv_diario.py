"""Carga diária do pacote SIconv (emendas parlamentares).

Testes PUROS: não tocam rede nem banco. O que se protege aqui é o que quebrou
em produção em fontes parecidas — header com BOM, coluna renomeada pela fonte,
número em formato BR e upsert que afeta a mesma linha duas vezes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.connectors import siconv_downloads
from src.jobs import siconv_diario as job

COLS_EMENDA = [
    "id_proposta",
    "qualif_proponente",
    "cod_programa_emenda",
    "nr_emenda",
    "nome_parlamentar",
    "beneficiario_emenda",
    "ind_impositivo",
    "tipo_parlamentar",
    "valor_repasse_proposta_emenda",
    "valor_repasse_emenda",
]
COLS_PROPOSTA = ["id_proposta", "cod_munic_ibge", "nr_proposta", "ano_prop", "uf_proponente"]


def test_normalizar_coluna_tira_acento_e_caixa():
    assert job.normalizar_coluna("NR_EMENDA") == "nr_emenda"
    assert job.normalizar_coluna("Município Proponente") == "municipio_proponente"
    assert job.normalizar_coluna("  ") == "coluna"


def test_colunas_do_csv_remove_bom_e_desambigua_repetida(tmp_path: Path):
    """A fonte manda UTF-8 com BOM: sem `utf-8-sig` a primeira coluna nasceria
    com um caractere invisível no nome e nenhum de-para casaria com ela."""
    arquivo = tmp_path / "emenda.csv"
    arquivo.write_text("ID_PROPOSTA;NR_EMENDA;NR_EMENDA\n1;2;3\n", encoding="utf-8-sig")

    assert job.colunas_do_csv(arquivo) == ["id_proposta", "nr_emenda", "nr_emenda_1"]


def test_coluna_ausente_vira_null_em_vez_de_quebrar():
    """Fonte que renomeia uma coluna não pode derrubar a carga inteira."""
    assert job.col(COLS_EMENDA, "e", "nr_emenda") == "e.nr_emenda"
    assert job.col(COLS_EMENDA, "e", "coluna_que_nao_existe") == "NULL::text"


def test_numero_decide_pela_virgula():
    """`1.234,56` é BR (ponto = milhar); `1234.56` já é decimal. Converter às
    cegas transformaria o segundo em 123456."""
    expr = job.numero("e.valor_repasse_emenda")
    assert "position(',' in e.valor_repasse_emenda) > 0" in expr
    assert "::numeric" in expr


def test_ibge_so_aceita_sete_digitos():
    assert "^[0-9]{7}$" in job.ibge("p.cod_munic_ibge")


def test_sql_upsert_protege_contra_linha_repetida_e_nao_usa_returning():
    sql = job.sql_upsert_emendas(COLS_EMENDA, COLS_PROPOSTA)

    # Sem DISTINCT ON, emenda repetida no arquivo faz o Postgres recusar o
    # comando ("cannot affect row a second time").
    assert "DISTINCT ON (e.id_proposta, e.nr_emenda)" in sql
    assert "ON CONFLICT (fonte, id_externo) DO UPDATE" in sql
    # RETURNING leria a linha sob a policy de SELECT (RLS por município) e o job
    # roda sem tenant: reportaria zero com a tabela cheia (§41).
    assert "RETURNING" not in sql.upper()
    assert "LEFT JOIN stg_proposta p ON p.id_proposta = e.id_proposta" in sql


def test_sql_upsert_sobrevive_a_proposta_sem_as_colunas_esperadas():
    sql = job.sql_upsert_emendas(COLS_EMENDA, ["id_proposta"])
    assert "NULL::text" in sql
    assert "ON CONFLICT" in sql


def test_proveniencia_marca_o_ano_como_derivado():
    """A fonte NÃO publica o ano da emenda. Gravamos o da proposta para o filtro
    de safra funcionar — e dizemos isso, para ninguém ler como dado da emenda."""
    sql = job.sql_upsert_emendas(COLS_EMENDA, COLS_PROPOSTA)
    assert "derivado:proposta.ANO_PROP" in sql


def test_catalogo_carrega_apenas_o_que_tem_destino():
    assert siconv_downloads.CARREGADAS == ("emenda", "proposta")
    # As tabelas de execução estão mapeadas, mas não se baixa centenas de MB
    # sem destino no schema.
    assert not siconv_downloads.ARQUIVOS["empenho"].carrega


def test_candidatos_de_nome_do_zip():
    assert siconv_downloads.ARQUIVOS["emenda"].nomes() == ("siconv_emenda.zip", "emenda.zip")


def test_proxima_execucao_nunca_e_agora():
    """Zero faria o loop girar em falso e repetir a carga várias vezes na hora."""
    agora = datetime(2026, 8, 19, job.HORA_UTC, 0, 0, tzinfo=UTC)
    assert job._segundos_ate_proxima_execucao(agora) == 24 * 3600


# --------------------------------------------------------------------------
# integração — o SQL roda de verdade contra o Postgres
# --------------------------------------------------------------------------

_EMENDA_CSV = (
    "ID_PROPOSTA;QUALIF_PROPONENTE;COD_PROGRAMA_EMENDA;NR_EMENDA;NOME_PARLAMENTAR;"
    "BENEFICIARIO_EMENDA;IND_IMPOSITIVO;TIPO_PARLAMENTAR;"
    "VALOR_REPASSE_PROPOSTA_EMENDA;VALOR_REPASSE_EMENDA\n"
    "901;Municipal;5620240001;71260013;DÉCIO LIMA;95996104000104;SIM;"
    "INDIVIDUAL;100000;1.234.567,89\n"
    "901;Municipal;5620240001;25700007;Bancada do Pará;95996104000104;NAO;"
    "BANCADA;98200;98200\n"
    # mesma (id_proposta, nr_emenda) repetida: sem DISTINCT ON o Postgres recusa
    "901;Municipal;5620240001;71260013;DÉCIO LIMA;95996104000104;SIM;"
    "INDIVIDUAL;100000;1.234.567,89\n"
    # proposta inexistente no outro arquivo: entra com município nulo, não some
    "999;Estadual;5620240002;36310006;Geraldo Magela;00394742000149;;INDIVIDUAL;5000;5000\n"
    # sem número de emenda: descartada
    "902;Municipal;5620240003;;Fulano;123;;INDIVIDUAL;10;10\n"
)

_PROPOSTA_CSV = (
    "ID_PROPOSTA;UF_PROPONENTE;MUNIC_PROPONENTE;COD_MUNIC_IBGE;NR_PROPOSTA;ANO_PROP;"
    "OBJETO_PROPOSTA;SIT_PROPOSTA\n"
    "901;SC;MONTE CARLO;4211272;014275/2024;2024;Construção de UBS;"
    "Proposta/Plano de Trabalho Aprovados\n"
)


async def _rodar_carga(tmp_path: Path) -> list[dict]:
    from sqlalchemy import text as sql_text

    from src.db.session import engine

    emenda = tmp_path / "emenda.csv"
    proposta = tmp_path / "proposta.csv"
    emenda.write_text(_EMENDA_CSV, encoding="utf-8-sig")
    proposta.write_text(_PROPOSTA_CSV, encoding="utf-8-sig")

    async with engine.begin() as conn:
        gravadas = await job.aplicar_carga(conn, {"emenda": emenda, "proposta": proposta})
    assert gravadas == 3

    from tests.conftest import _owner_engine

    # A leitura TAMBÉM precisa da bandeira: `proposta_emendas` está sob FORCE
    # RLS, então nem o owner escapa da policy por município. Sem isto o teste
    # veria só a linha sem território e leria como "não gravou".
    async with _owner_engine.begin() as conn:
        await conn.execute(sql_text("SELECT set_config('app.plataforma', 'on', true)"))
        linhas = (
            await conn.execute(
                sql_text(
                    "SELECT id_externo, numero_emenda, numero_proposta, municipio_ibge, ano, "
                    "tipo_emenda, parlamentar, valor, detalhe, proveniencia "
                    "FROM proposta_emendas WHERE fonte = 'siconv' ORDER BY id_externo"
                )
            )
        ).mappings()
        return [dict(r) for r in linhas]


async def test_carga_de_ponta_a_ponta(tmp_path: Path):
    from decimal import Decimal

    linhas = await _rodar_carga(tmp_path)

    # 3 emendas: a repetida colapsa, a sem número é descartada
    assert [linha["id_externo"] for linha in linhas] == [
        "901|25700007",
        "901|71260013",
        "999|36310006",
    ]

    individual = next(linha for linha in linhas if linha["numero_emenda"] == "71260013")
    # o join carimbou o território — é ele que faz a emenda aparecer no painel
    assert individual["municipio_ibge"] == "4211272"
    assert individual["numero_proposta"] == "014275/2024"
    assert individual["ano"] == 2024
    assert individual["parlamentar"] == "DÉCIO LIMA"
    assert individual["tipo_emenda"] == "INDIVIDUAL"
    # `1.234.567,89` é BR: ponto de milhar fora, vírgula vira decimal
    assert individual["valor"] == Decimal("1234567.89")
    assert individual["detalhe"]["municipio_nome"] == "MONTE CARLO"
    assert individual["proveniencia"]["ano"].startswith("derivado:")

    # emenda cuja proposta não veio no arquivo entra sem território, não some
    orfa = next(linha for linha in linhas if linha["id_externo"] == "999|36310006")
    assert orfa["municipio_ibge"] is None and orfa["numero_proposta"] is None


async def test_carga_e_idempotente(tmp_path: Path):
    """Rodar de novo no mesmo dia atualiza, não duplica — é um job diário."""
    await _rodar_carga(tmp_path)
    linhas = await _rodar_carga(tmp_path)
    assert len(linhas) == 3
