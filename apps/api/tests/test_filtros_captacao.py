"""Filtros de captação (busca, natureza jurídica, modalidade, órgão,
qualificação, ano, ordenação), facetas dos dropdowns, resumo consolidado,
relatório CSV — e a lente de emendas parlamentares sobre os recebidos."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from src.db.session import rls_session
from src.services import propostas as prop_service
from src.services import repasses as rep_service

from .conftest import _owner_engine


# ── ano de referência (puro) ────────────────────────────────────────────────
def test_ano_de_prefere_criacao_a_atualizacao() -> None:
    from src.models.proposta import Proposta

    # criada em 2022 e movimentada em 2026 — a proposta é de 2022
    p = Proposta(data_proposta=date(2022, 3, 1), data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) == "2022"

    # sem data de criação, vale o ano embutido no nº da proposta
    p = Proposta(numero_proposta="043210/2024", data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) == "2024"

    # sem criação nem nº com ano: o exercício da execução
    p = Proposta(execucao={"ano": "2023"}, data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) == "2023"

    # sem NENHUM sinal de criação o ano é indefinido — a movimentação de 2026
    # não promove a proposta à safra 2026
    p = Proposta(data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) is None

    # sufixo implausível não vira ano ("12/3456" não é uma safra)
    p = Proposta(numero_proposta="12/3456", data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) is None

    # exercício lixo também não vira safra
    p = Proposta(execucao={"ano": "26"}, data_atualizacao_fonte=date(2026, 1, 5))
    assert prop_service.ano_de(p) is None


# ── classificador de natureza jurídica (puro) ───────────────────────────────
def test_classificar_natureza_juridica() -> None:
    assert prop_service.classificar_natureza_juridica("Administração Pública Municipal") == (
        "municipal"
    )
    assert prop_service.classificar_natureza_juridica("Prefeitura Municipal") == "municipal"
    assert prop_service.classificar_natureza_juridica("Adm. Pública Estadual") == "estadual_df"
    assert prop_service.classificar_natureza_juridica("Distrito Federal") == "estadual_df"
    assert prop_service.classificar_natureza_juridica("Consórcio Público") == "consorcio"
    assert prop_service.classificar_natureza_juridica("Sociedade de Economia Mista") == (
        "empresa_publica"
    )
    assert prop_service.classificar_natureza_juridica("Organização da Sociedade Civil") == "osc"
    assert prop_service.classificar_natureza_juridica("Autarquia federal") == "outros"
    assert prop_service.classificar_natureza_juridica(None) is None


async def _seed(
    id_externo: str,
    ibge: str,
    *,
    fonte: str = "transferegov_ff",
    titulo: str = "Programa",
    orgao: str = "Ministério da Saúde",
    modalidade: str = "Convênio",
    situacao: str = "Empenhada",
    valor: str = "100000",
    execucao: str | None = None,
    prazos: str | None = None,
    uf: str | None = None,
    municipio_nome: str | None = None,
    data_fonte: str | None = None,
    data_proposta: str | None = None,
    numero: str | None = None,
    categorias: str | None = None,
) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, orgao_superior, "
                "modalidade, situacao, municipio_ibge, municipio_nome, uf, valor_total, "
                "execucao, prazos, data_atualizacao_fonte, data_proposta, "
                "numero_proposta, categorias_ia, cache_atualizado_em) "
                "VALUES (:f,:e,:t,:o,:m,:s,:ibge,:nome,:uf,:v,"
                "CAST(:ex AS jsonb), CAST(:p AS jsonb), :d, :dp, :num, "
                "CAST(:cat AS jsonb), now())"
            ),
            {
                "f": fonte,
                "e": id_externo,
                "t": titulo,
                "o": orgao,
                "m": modalidade,
                "s": situacao,
                "ibge": ibge,
                "nome": municipio_nome,
                "uf": uf,
                "v": valor,
                "ex": execucao,
                "p": prazos,
                "d": date.fromisoformat(data_fonte) if data_fonte else None,
                "dp": date.fromisoformat(data_proposta) if data_proposta else None,
                "num": numero,
                "cat": categorias,
            },
        )


EXEC_MUNICIPAL = (
    '{"natureza_juridica": "Administração Pública Municipal", "ano": "2025", '
    '"tipo_transferencia": "Voluntária", "valor_global": "200000", '
    '"valor_empenhado": "150000", "valor_liberado": "80000", "valor_pago": "60000", '
    '"data_inicio_vigencia": "2025-01-10", "data_fim_vigencia": "2099-12-31"}'
)
EXEC_CONSORCIO = (
    '{"natureza_juridica": "Consórcio Público", "ano": "2024", '
    '"tipo_transferencia": "Especial", "valor_global": "50000"}'
)


# ── safra: o filtro/faceta de ano segue a criação ───────────────────────────
async def test_safra_nao_vem_da_movimentacao(seed_user, seed_municipio) -> None:
    """Movimentação em 2026 não promove nada à safra 2026 — nem cria safra do nada."""
    u = await seed_user("safra@x.com")
    await seed_municipio(u, "3550308")
    # criada em 2022, movimentada em 2026
    await _seed("C1", "3550308", data_proposta="2022-03-01", data_fonte="2026-01-30")
    # sem nenhum sinal de criação, só movimentação
    await _seed("C2", "3550308", data_fonte="2026-01-30")

    async with rls_session(u) as s:
        de_2022, _ = await prop_service.listar_pagina(s, ano="2022")
        de_2026, _ = await prop_service.listar_pagina(s, ano="2026")
        todas, _ = await prop_service.listar_pagina(s)
        facetas = await prop_service.facetas(s)

    assert [p.id_externo for p in de_2022] == ["C1"]
    assert de_2026 == []
    # sem ano a proposta não some da lista — só fica fora das safras
    assert {p.id_externo for p in todas} == {"C1", "C2"}
    assert [o["valor"] for o in facetas["ano"]] == ["2022"]


# ── busca textual, dimensões e ordenação ────────────────────────────────────
async def test_filtros_de_captacao(seed_user, seed_municipio) -> None:
    u = await seed_user("filtros@x.com")
    await seed_municipio(u, "3550308")
    await _seed("A1", "3550308", titulo="Ampliação de UBS", execucao=EXEC_MUNICIPAL)
    await _seed(
        "B2",
        "3550308",
        titulo="Quadra poliesportiva",
        orgao="Ministério do Esporte",
        modalidade="Termo de Compromisso",
        situacao="Disponível para propostas",
        valor="900000",
        execucao=EXEC_CONSORCIO,
    )

    async with rls_session(u) as s:
        # busca livre: por programa, órgão ou código
        assert [p.id_externo for p in await prop_service.listar(s, q="UBS")] == ["A1"]
        assert [p.id_externo for p in await prop_service.listar(s, q="esporte")] == ["B2"]
        assert [p.id_externo for p in await prop_service.listar(s, q="B2")] == ["B2"]

        # natureza jurídica elegível (derivada do jsonb de execução)
        municipais = await prop_service.listar(s, natureza_juridica="municipal")
        assert [p.id_externo for p in municipais] == ["A1"]
        assert await prop_service.listar(s, natureza_juridica="osc") == []

        # modalidade, órgão, qualificação e ano
        assert [p.id_externo for p in await prop_service.listar(s, modalidade="Convênio")] == ["A1"]
        assert [
            p.id_externo for p in await prop_service.listar(s, orgao="Ministério do Esporte")
        ] == ["B2"]
        assert [p.id_externo for p in await prop_service.listar(s, qualificacao="Especial")] == [
            "B2"
        ]
        assert [p.id_externo for p in await prop_service.listar(s, ano="2025")] == ["A1"]

        # ordenação
        assert [p.id_externo for p in await prop_service.listar(s, ordenar="nome")] == ["A1", "B2"]
        # "Ministério da Saúde" < "Ministério do Esporte" (A-Z)
        assert [p.id_externo for p in await prop_service.listar(s, ordenar="orgao")] == [
            "A1",
            "B2",
        ]
        assert [p.id_externo for p in await prop_service.listar(s, ordenar="valor")] == [
            "B2",
            "A1",
        ]


async def test_ordenacao_por_prazo(seed_user, seed_municipio) -> None:
    u = await seed_user("prazos@x.com")
    await seed_municipio(u, "3550308")
    await _seed("PERTO", "3550308", prazos='[{"tipo":"envio","data_limite":"2030-01-01"}]')
    await _seed("LONGE", "3550308", prazos='[{"tipo":"envio","data_limite":"2040-01-01"}]')
    await _seed("SEMPRAZO", "3550308")

    async with rls_session(u) as s:
        proximos = await prop_service.listar(s, ordenar="prazo")
        assert [p.id_externo for p in proximos] == ["PERTO", "LONGE", "SEMPRAZO"]
        distantes = await prop_service.listar(s, ordenar="prazo_distante")
        # sem prazo vai para o fim nas DUAS direções
        assert [p.id_externo for p in distantes] == ["LONGE", "PERTO", "SEMPRAZO"]


# ── paginação (o painel carrega de página em página) ────────────────────────
async def test_paginacao_caminho_rapido(seed_user, seed_municipio) -> None:
    """Sem pós-filtro e na ordenação do SQL, o LIMIT/OFFSET desce ao banco."""
    u = await seed_user("pagina@x.com")
    await seed_municipio(u, "3550308")
    for i in range(5):
        await _seed(f"P{i}", "3550308")

    async with rls_session(u) as s:
        primeira, total = await prop_service.listar_pagina(s, limite=2)
        assert total == 5  # o total é do recorte, não da página
        assert len(primeira) == 2

        segunda, total_2 = await prop_service.listar_pagina(s, limite=2, offset=2)
        assert total_2 == 5
        # páginas não se sobrepõem nem pulam linhas — mesmo com
        # `cache_atualizado_em` empatado (todas gravadas no mesmo instante)
        terceira, _ = await prop_service.listar_pagina(s, limite=2, offset=4)
        vistos = [p.id_externo for p in [*primeira, *segunda, *terceira]]
        assert sorted(vistos) == ["P0", "P1", "P2", "P3", "P4"]

        # sem limite continua devolvendo tudo (facetas, resumo e CSV dependem)
        todas, total_3 = await prop_service.listar_pagina(s)
        assert len(todas) == total_3 == 5


async def test_paginacao_depois_do_pos_filtro(seed_user, seed_municipio) -> None:
    """Com filtro/ordenação que rodam em Python, a página sai DEPOIS deles.

    Aqui está a armadilha: um LIMIT ingênuo no SQL recortaria o conjunto
    pré-filtro e devolveria a página errada (e um total inflado).
    """
    u = await seed_user("pagina2@x.com")
    await seed_municipio(u, "3550308")
    # 3 de 2025 (entram no filtro de ano) e 2 de 2024 (não entram)
    for nome in ("Creche", "Ambulância", "Escola"):
        await _seed(nome, "3550308", titulo=nome, execucao=EXEC_MUNICIPAL)
    for nome in ("Praça", "Ponte"):
        await _seed(nome, "3550308", titulo=nome, execucao=EXEC_CONSORCIO)

    async with rls_session(u) as s:
        # ano=2025 é pós-filtro em Python; ordenar=nome também reordena depois
        pagina, total = await prop_service.listar_pagina(
            s, ano="2025", ordenar="nome", limite=2
        )
        assert total == 3  # só as de 2025 — não as 5 do SQL
        assert [p.titulo for p in pagina] == ["Ambulância", "Creche"]

        resto, total_2 = await prop_service.listar_pagina(
            s, ano="2025", ordenar="nome", limite=2, offset=2
        )
        assert total_2 == 3
        assert [p.titulo for p in resto] == ["Escola"]


# ── facetas: as opções dos dropdowns, com contagem ──────────────────────────
async def test_facetas_ignoram_a_propria_dimensao(seed_user, seed_municipio) -> None:
    u = await seed_user("facetas@x.com")
    await seed_municipio(u, "3550308")
    await _seed("A1", "3550308", execucao=EXEC_MUNICIPAL)
    await _seed("B2", "3550308", modalidade="Termo de Compromisso", execucao=EXEC_CONSORCIO)

    async with rls_session(u) as s:
        facetas = await prop_service.facetas(s)
        assert {o["valor"] for o in facetas["modalidade"]} == {"Convênio", "Termo de Compromisso"}
        assert {o["valor"] for o in facetas["natureza_juridica"]} == {"municipal", "consorcio"}
        assert all(o["total"] == 1 for o in facetas["modalidade"])
        assert (
            facetas["natureza_juridica"][0]["rotulo"]
            in dict(prop_service.NATUREZAS_JURIDICAS).values()
        )

        # com um filtro aplicado, a dimensão FILTRADA continua mostrando tudo
        # (senão o dropdown ficaria preso), mas as outras encolhem
        com_filtro = await prop_service.facetas(s, modalidade="Convênio")
        assert {o["valor"] for o in com_filtro["modalidade"]} == {
            "Convênio",
            "Termo de Compromisso",
        }
        assert {o["valor"] for o in com_filtro["natureza_juridica"]} == {"municipal"}


# ── dimensões novas do painel: UF, mês, município e categoria ───────────────
async def test_filtra_por_uf_mes_e_categoria(seed_user, seed_municipio) -> None:
    u = await seed_user("dimensoes@x.com")
    await seed_municipio(u, "3550308")
    await seed_municipio(u, "2311801")
    await _seed(
        "SP1",
        "3550308",
        titulo="Ampliação de UBS",
        uf="SP",
        municipio_nome="São Paulo",
        prazos='[{"tipo":"envio","data_limite":"2030-03-20"}]',
    )
    await _seed(
        "CE1",
        "2311801",
        titulo="Pavimentação de vias urbanas",
        orgao="Ministério das Cidades",
        uf="CE",
        municipio_nome="Russas",
        data_fonte="2030-07-05",
    )

    async with rls_session(u) as s:
        assert [p.id_externo for p in await prop_service.listar(s, uf="SP")] == ["SP1"]
        assert [p.id_externo for p in await prop_service.listar(s, uf="ce")] == ["CE1"]

        # mês: o do prazo final quando existe…
        assert [p.id_externo for p in await prop_service.listar(s, mes="03")] == ["SP1"]
        # …e o da atualização na fonte quando não há prazo declarado
        assert [p.id_externo for p in await prop_service.listar(s, mes="07")] == ["CE1"]
        assert await prop_service.listar(s, mes="12") == []

        # categoria: pílula derivada do texto, mesmo sem curadoria gravada
        assert [p.id_externo for p in await prop_service.listar(s, categoria="saude")] == ["SP1"]
        assert [p.id_externo for p in await prop_service.listar(s, categoria="infraestrutura")] == [
            "CE1"
        ]

        # município continua recortando (agora também como dimensão de faceta)
        assert [p.id_externo for p in await prop_service.listar(s, municipio="2311801")] == ["CE1"]


async def test_categoria_curada_vence_a_classificacao_na_hora(seed_user, seed_municipio) -> None:
    """`categorias_ia` gravada (pela IA) manda; sem ela, classifica pelo texto."""
    u = await seed_user("curada@x.com")
    await seed_municipio(u, "3550308")
    await _seed("CUR", "3550308", titulo="Ampliação de UBS", categorias='["cultura"]')

    async with rls_session(u) as s:
        assert [p.id_externo for p in await prop_service.listar(s, categoria="cultura")] == ["CUR"]
        assert await prop_service.listar(s, categoria="saude") == []


async def test_facetas_das_dimensoes_novas(seed_user, seed_municipio) -> None:
    u = await seed_user("facetas-novas@x.com")
    await seed_municipio(u, "3550308")
    await seed_municipio(u, "2311801")
    await _seed(
        "SP1",
        "3550308",
        titulo="Ampliação de UBS",
        uf="SP",
        municipio_nome="São Paulo",
        data_fonte="2030-03-10",
    )
    await _seed(
        "CE1",
        "2311801",
        titulo="Pavimentação de vias",
        uf="CE",
        municipio_nome="Russas",
        data_fonte="2030-07-05",
    )

    async with rls_session(u) as s:
        facetas = await prop_service.facetas(s)
        # município: rótulo legível (nome/UF), não o código IBGE cru
        assert {o["valor"] for o in facetas["municipio"]} == {"3550308", "2311801"}
        assert {"São Paulo/SP", "Russas/CE"} == {o["rotulo"] for o in facetas["municipio"]}
        assert {o["valor"] for o in facetas["uf"]} == {"SP", "CE"}
        assert {o["valor"] for o in facetas["categoria"]} == {"saude", "infraestrutura"}
        assert dict(prop_service.MESES)["03"] == "Março"
        # meses saem em ordem cronológica, não por contagem
        assert [o["valor"] for o in facetas["mes"]] == ["03", "07"]
        assert [o["rotulo"] for o in facetas["mes"]] == ["Março", "Julho"]

        # o filtro de município não pode fechar o próprio dropdown de município
        com_municipio = await prop_service.facetas(s, municipio="2311801")
        assert {o["valor"] for o in com_municipio["municipio"]} == {"3550308", "2311801"}
        assert {o["valor"] for o in com_municipio["uf"]} == {"CE"}


# ── resumo consolidado ──────────────────────────────────────────────────────
async def test_resumo_consolida_cards_serie_e_vigentes(seed_user, seed_municipio) -> None:
    u = await seed_user("resumo@x.com")
    await seed_municipio(u, "3550308")
    await _seed("A1", "3550308", execucao=EXEC_MUNICIPAL)
    await _seed("B2", "3550308", situacao="Edital aberto", execucao=EXEC_CONSORCIO)

    async with rls_session(u) as s:
        resumo = await prop_service.resumo(s)

    cards = resumo["cards"]
    assert cards["valor_conveniado"] == 250000  # 200k + 50k
    assert cards["valor_desembolsado"] == 80000  # liberado da A1
    assert cards["valor_a_utilizar"] == 90000  # empenhado 150k − pago 60k
    assert cards["oportunidades_abertas"] == 1  # "Edital aberto" → disponível
    assert cards["convenios_iniciados"] == 1
    assert cards["convenios_em_execucao"] == 1

    assert [a["ano"] for a in resumo["por_ano"]] == ["2024", "2025"]
    assert sum(p["quantidade"] for p in resumo["pipeline"]) == 2

    vigente = resumo["convenios_vigentes"][0]
    assert vigente["percentual_desembolso"] == 40.0  # 80k de 200k
    assert vigente["dias_restantes"] > 0


# ── relatório CSV ───────────────────────────────────────────────────────────
async def test_relatorio_csv(seed_user, seed_municipio) -> None:
    u = await seed_user("csv@x.com")
    await seed_municipio(u, "3550308")
    await _seed("A1", "3550308", titulo="Ampliação de UBS", execucao=EXEC_MUNICIPAL)

    async with rls_session(u) as s:
        csv = prop_service.gerar_csv(await prop_service.listar(s))

    cabecalho, linha = csv.splitlines()[:2]
    assert cabecalho.startswith("fonte;codigo;")
    assert "Ampliação de UBS" in linha
    assert "municipal" in linha
    assert "150000" in linha  # empenhado


# ── emendas parlamentares (lente sobre os recebidos) ────────────────────────
async def _seed_emenda(
    id_externo: str,
    ibge: str,
    *,
    parlamentar: str,
    partido: str = "PX",
    modalidade: str = "individual",
    funcao: str = "Saúde",
    ano: str = "2025",
    empenhado: str = "100000",
    pago: str = "40000",
) -> None:
    detalhe = (
        f'{{"parlamentar": "{parlamentar}", "partido": "{partido}", '
        f'"modalidade": "{modalidade}", "funcao": "{funcao}", "ano": "{ano}", '
        f'"valor_empenhado": "{empenhado}", "valor_pago": "{pago}"}}'
    )
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO repasses (fonte, id_externo, municipio_ibge, valor, "
                "natureza, categoria, orgao_superior, emenda, detalhe, cache_atualizado_em) "
                "VALUES ('emendas',:e,:ibge,:v,'repasse',:cat,'Ministério da Saúde',true,"
                "CAST(:d AS jsonb), now())"
            ),
            {"e": id_externo, "ibge": ibge, "v": pago, "cat": funcao, "d": detalhe},
        )


async def test_resumo_emendas(seed_user, seed_municipio, seed_repasse) -> None:
    u = await seed_user("emendas@x.com")
    await seed_municipio(u, "3550308")
    await _seed_emenda("E1", "3550308", parlamentar="Fulana de Tal")
    await _seed_emenda(
        "E2",
        "3550308",
        parlamentar="Beltrano",
        modalidade="bancada",
        funcao="Educação",
        ano="2024",
        empenhado="50000",
        pago="50000",
    )
    # repasse comum (não-emenda) não entra na lente
    await seed_repasse("fpm", "R1", "3550308", valor="777")

    async with rls_session(u) as s:
        resumo = await rep_service.resumo_emendas(s)

    assert resumo.emendas == 2
    assert resumo.empenhado == 150000
    assert resumo.pago == 90000
    assert resumo.percentual_executado == 60.0
    assert [r.parlamentar for r in resumo.ranking_parlamentares] == ["Beltrano", "Fulana de Tal"]
    assert {d.chave for d in resumo.por_modalidade} == {"individual", "bancada"}
    assert {d.chave for d in resumo.por_area} == {"Saúde", "Educação"}
    assert resumo.opcoes.anos == ["2025", "2024"]
    assert resumo.opcoes.parlamentares == ["Beltrano", "Fulana de Tal"]

    # filtro por parlamentar recorta a lista mas NÃO esvazia o dropdown
    async with rls_session(u) as s:
        so_beltrano = await rep_service.resumo_emendas(s, parlamentar="Beltrano")
    assert so_beltrano.emendas == 1
    assert so_beltrano.itens[0].modalidade == "bancada"
    assert so_beltrano.itens[0].percentual_executado == 100.0
    assert so_beltrano.opcoes.parlamentares == ["Beltrano", "Fulana de Tal"]


async def test_csv_emendas(seed_user, seed_municipio) -> None:
    u = await seed_user("csvemendas@x.com")
    await seed_municipio(u, "3550308")
    await _seed_emenda("E1", "3550308", parlamentar="Fulana de Tal")

    async with rls_session(u) as s:
        csv = rep_service.gerar_csv_emendas(await rep_service.listar_emendas(s))

    cabecalho, linha = csv.splitlines()[:2]
    assert cabecalho.startswith("codigo;numero;parlamentar;")
    assert "Fulana de Tal" in linha
    assert "40.0" in linha  # % executado (40k de 100k)
