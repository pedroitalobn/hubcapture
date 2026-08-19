"""Carga diária do pacote SIconv — emendas parlamentares no banco do Hub.

O QUE FAZ, todo dia: baixa os ZIPs nacionais do SIconv (`emenda` e `proposta`),
descompacta, carrega cada CSV numa tabela temporária via `COPY` e faz UM upsert
em `proposta_emendas`. Idempotente: rodar duas vezes no mesmo dia não duplica
nada (a chave é `(fonte, id_externo)`).

POR QUE ASSIM
-------------
- **O join mora no Postgres, não em Python.** `emenda` tem centenas de milhares
  de linhas e `proposta` passa de 1 GB descompactado; casar isso em memória
  estouraria o worker. Com `COPY` + `INSERT … SELECT` o banco faz o trabalho e
  a memória do processo fica constante.
- **Temp table `ON COMMIT DROP`.** Sem isso a staging sobreviveria à transação e
  voltaria ao pool grudada na conexão. E temp table dispensa GRANT de CREATE.
- **Colunas descobertas do próprio arquivo.** O header do CSV vira o schema da
  staging; coluna que a fonte renomear simplesmente chega como NULL em vez de
  derrubar a carga inteira (mesma disciplina do §27).
- **Sem `RETURNING` no upsert.** `proposta_emendas` está sob `FORCE RLS` e o job
  roda sem tenant: as policies de INSERT/UPDATE são `true`, mas a de SELECT
  recorta por município — um `RETURNING` leria zero linhas e reportaria "0
  gravadas" com a tabela cheia (o mesmo tropeço documentado na §41). A contagem
  sai do `rowcount`.

O QUE NÃO VEM DA FONTE (e por isso não é inventado aqui): o **ano da emenda** —
`NR_EMENDA` é código do autor + sequencial, não carrega ano. Gravamos `ano` a
partir de `proposta.ANO_PROP` para o filtro de safra funcionar, e registramos
isso em `proveniencia` para ninguém ler como se fosse dado da emenda. **Partido
e UF do parlamentar** também não existem no pacote — vêm do connector `emendas`
(Portal da Transparência) quando ele estiver ligado.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import tempfile
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..connectors import siconv_downloads
from ..connectors.siconv_downloads import CARREGADAS, DownloadError
from ..db.session import engine
from ..services import config as config_service

log = logging.getLogger(__name__)

FONTE = "siconv"

HORA_UTC = int(os.getenv("SICONV_DIARIO_HORA_UTC", "7"))
ATIVO = os.getenv("SICONV_DIARIO_ATIVO", "1") not in ("0", "false", "False")
# Trava global: duas réplicas do worker carregariam as MESMAS linhas em
# paralelo e disputariam o upsert. Advisory lock cai sozinha se o processo
# morrer — flag em tabela deixaria trava órfã.
LOCK_ID = 8_140_233_902

# Recorte operacional: `SICONV_TABELAS=emenda,proposta` baixa só o que interessa
# (a cadeia de execução custa centenas de MB a mais por dia). Vazio = catálogo.
_TABELAS_ENV = [t.strip() for t in os.getenv("SICONV_TABELAS", "").split(",") if t.strip()]


def tabelas_alvo() -> tuple[str, ...]:
    """As tabelas desta carga: o recorte do env, filtrado pelo catálogo."""
    if not _TABELAS_ENV:
        return CARREGADAS
    return tuple(t for t in CARREGADAS if t in _TABELAS_ENV)


ESCOPO_TERRITORIO = "territorio"
ESCOPO_NACIONAL = "nacional"
_ESCOPO_ENV = (os.getenv("SICONV_PROPOSTAS_ESCOPO") or "").strip().lower()


async def escopo_propostas() -> str:
    """`territorio` (padrão) ou `nacional` — painel admin sobrescreve o env.

    O padrão é o território porque `proposta.csv` é NACIONAL: carregá-lo inteiro
    são milhões de linhas (com o registro-fonte em jsonb junto) para um cache que
    só é lido por município. `nacional` existe para quem quer o país no banco e
    aceita o custo — a decisão é de operação, não de código.
    """
    do_painel = (await config_service.resolver("siconv_propostas_escopo") or "").strip().lower()
    valor = do_painel or _ESCOPO_ENV
    return ESCOPO_NACIONAL if valor == ESCOPO_NACIONAL else ESCOPO_TERRITORIO


async def ibges_do_territorio(conn: AsyncConnection) -> list[str]:
    """Municípios monitorados por QUALQUER usuário — o recorte da carga.

    Lê `municipios_interesse`, que é tabela por-tenant sob FORCE RLS: só a
    bandeira `app.plataforma` (ligada por `aplicar_carga`) enxerga o conjunto
    todo. Sem ela o job veria zero e a carga entregaria zero proposta em
    silêncio — o pior desfecho possível para uma coleta.
    """
    linhas = await conn.execute(
        text(
            "SELECT DISTINCT ibge FROM municipios_interesse "
            "WHERE ibge IS NOT NULL AND ibge ~ '^[0-9]{7}$'"
        )
    )
    return sorted(linha[0] for linha in linhas)


# --------------------------------------------------------------------------
# leitura do CSV → schema da staging
# --------------------------------------------------------------------------


def normalizar_coluna(nome: str) -> str:
    """`NR_EMENDA` → `nr_emenda`. Sem acento, sem espaço, seguro como identificador."""
    sem_acento = unicodedata.normalize("NFD", nome or "")
    limpo = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn").strip().lower()
    saida = "".join(c if c.isalnum() else "_" for c in limpo).strip("_")
    return saida or "coluna"


def colunas_do_csv(caminho: Path, delimitador: str = ";") -> list[str]:
    """Nomes das colunas do header, normalizados e SEM repetição.

    O arquivo vem em UTF-8 com BOM — `utf-8-sig` remove o BOM, senão a primeira
    coluna nasceria com um caractere invisível grudado no nome.
    """
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        cabecalho = next(csv.reader(f, delimiter=delimitador), [])

    vistas: dict[str, int] = {}
    colunas: list[str] = []
    for bruto in cabecalho:
        nome = normalizar_coluna(bruto)
        if nome in vistas:
            vistas[nome] += 1
            nome = f"{nome}_{vistas[nome]}"
        else:
            vistas[nome] = 0
        colunas.append(nome)
    return colunas


# --------------------------------------------------------------------------
# expressões SQL de conversão (o CSV é 100% texto)
# --------------------------------------------------------------------------


def col(colunas: list[str], tabela: str, nome: str) -> str:
    """`t.coluna` quando ela existe no arquivo; `NULL` quando a fonte a renomeou."""
    return f"{tabela}.{nome}" if nome in colunas else "NULL::text"


def numero_br(expr: str) -> str:
    """Texto → numeric, aceitando `1.234,56` (BR) e `1234.56`.

    A decisão é pela VÍRGULA: com ela, o ponto é separador de milhar; sem ela, o
    ponto já é decimal. Converter às cegas transformaria `1234.56` em `123456`.
    """
    br = (
        f"CASE WHEN position(',' in {expr}) > 0 "
        f"THEN replace(replace({expr}, '.', ''), ',', '.') ELSE {expr} END"
    )
    limpo = f"regexp_replace(coalesce({br}, ''), '[^0-9.-]', '', 'g')"
    return f"(CASE WHEN {limpo} ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN {limpo}::numeric END)"


def ano(expr: str) -> str:
    """Primeiro grupo de 4 dígitos → int. Lixo na coluna vira NULL, não erro."""
    return f"(NULLIF(substring(coalesce({expr}, '') from '[0-9]{{4}}'), '')::int)"


def ibge(expr: str) -> str:
    """Só aceita código de 7 dígitos — a coluna é `varchar(7)` e meia chave
    truncada apontaria para o município errado."""
    digitos = f"regexp_replace(coalesce({expr}, ''), '[^0-9]', '', 'g')"
    return f"(CASE WHEN {digitos} ~ '^[0-9]{{7}}$' THEN {digitos} END)"


def data(expr: str) -> str:
    """Texto → date, aceitando `DD/MM/AAAA` (SIconv) e `AAAA-MM-DD`.

    `to_date` e não `::date`: uma linha suja não pode abortar a carga inteira —
    mesma disciplina do backfill da §43.
    """
    e = f"btrim(coalesce({expr}, ''))"
    return (
        f"(CASE WHEN {e} ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' "
        f"THEN to_date({e}, 'DD/MM/YYYY') "
        f"WHEN {e} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' "
        f"THEN to_date(left({e}, 10), 'YYYY-MM-DD') END)"
    )


def data_componentes(dia: str, mes: str, ano: str, unica: str) -> str:
    """Data de CRIAÇÃO da proposta, remontada de DIA_PROP + MES_PROP + ANO_PROP.

    São as variáveis oficiais do SIconv (§35b) e elas vencem qualquer coluna
    única de data: as retaguardas (vigência, cadastro) marcavam a proposta com
    uma data que não é a dela. `make_date` levantaria em linha suja; a
    montagem por texto + `to_date` degrada para NULL, como no resto da carga.
    """
    d = f"lpad(regexp_replace(coalesce({dia}, ''), '[^0-9]', '', 'g'), 2, '0')"
    m = f"lpad(regexp_replace(coalesce({mes}, ''), '[^0-9]', '', 'g'), 2, '0')"
    a = f"regexp_replace(coalesce({ano}, ''), '[^0-9]', '', 'g')"
    composta = (
        f"CASE WHEN {a} ~ '^[0-9]{{4}}$' AND {d} ~ '^(0[1-9]|[12][0-9]|3[01])$' "
        f"AND {m} ~ '^(0[1-9]|1[0-2])$' "
        f"THEN to_date({a} || '-' || {m} || '-' || {d}, 'YYYY-MM-DD') END"
    )
    return f"coalesce(({composta}), {data(unica)})"


def texto(expr: str, tamanho: int) -> str:
    """Recorta no limite da coluna: a fonte não promete tamanho e um valor longo
    abortaria a carga inteira por causa de uma linha."""
    return f"left(nullif(btrim({expr}), ''), {tamanho})"


# --------------------------------------------------------------------------
# staging
# --------------------------------------------------------------------------


async def carregar_staging(conn: AsyncConnection, tabela: str, caminho: Path) -> list[str]:
    """Cria `stg_<tabela>` a partir do header e despeja o CSV nela com COPY."""
    colunas = colunas_do_csv(caminho)
    if not colunas:
        raise DownloadError(f"{caminho.name} veio sem cabeçalho")

    corpo = ", ".join(f'"{c}" text' for c in colunas)
    await conn.execute(text(f"CREATE TEMP TABLE stg_{tabela} ({corpo}) ON COMMIT DROP"))

    raw = await conn.get_raw_connection()
    apg = raw.driver_connection  # asyncpg.Connection
    await apg.copy_to_table(
        f"stg_{tabela}",
        source=str(caminho),
        format="csv",
        delimiter=";",
        header=True,  # descarta a linha do cabeçalho (e o BOM junto com ela)
        null="",
        encoding="UTF8",
    )
    total = (await conn.execute(text(f"SELECT count(*) FROM stg_{tabela}"))).scalar_one()
    log.info(
        "siconv: staging %s carregada — %s linha(s), %d coluna(s)", tabela, total, len(colunas)
    )
    return colunas


def sql_upsert_emendas(cols_emenda: list[str], cols_proposta: list[str]) -> str:
    """O upsert de `proposta_emendas`, montado sobre as colunas que existem.

    `DISTINCT ON` é obrigatório: sem ele, emenda repetida no arquivo (ou
    `id_proposta` duplicado na proposta) faria o Postgres recusar o comando com
    "ON CONFLICT DO UPDATE command cannot affect row a second time".
    """
    e = lambda n: col(cols_emenda, "e", n)  # noqa: E731
    p = lambda n: col(cols_proposta, "p", n)  # noqa: E731

    assinado = numero_br(e("valor_repasse_emenda"))
    cadastrado = numero_br(e("valor_repasse_proposta_emenda"))
    # o valor ASSINADO manda; sem ele, o cadastrado na proposta
    valor = f"coalesce({assinado}, {cadastrado})"
    municipio = ibge(p("cod_munic_ibge"))
    parlamentar = texto(e("nome_parlamentar"), 255)
    tipo = texto(e("tipo_parlamentar"), 64)
    numero_emenda = texto(e("nr_emenda"), 64)

    return f"""
    INSERT INTO proposta_emendas (
        id, fonte, id_externo, numero_proposta, municipio_ibge,
        numero_emenda, ano, tipo_emenda, parlamentar, valor,
        detalhe, proveniencia, hash_conteudo, cache_atualizado_em
    )
    SELECT DISTINCT ON (e.id_proposta, e.nr_emenda)
        gen_random_uuid(),
        '{FONTE}',
        left(e.id_proposta || '|' || e.nr_emenda, 128),
        {texto(p("nr_proposta"), 64)},
        {municipio},
        {numero_emenda},
        {ano(p("ano_prop"))},
        {tipo},
        {parlamentar},
        {valor},
        jsonb_strip_nulls(jsonb_build_object(
            'id_proposta', e.id_proposta,
            'cod_programa_emenda', {e("cod_programa_emenda")},
            'beneficiario_emenda', {e("beneficiario_emenda")},
            'qualif_proponente', {e("qualif_proponente")},
            'ind_impositivo', {e("ind_impositivo")},
            'valor_repasse_proposta_emenda', {numero_br(e("valor_repasse_proposta_emenda"))},
            'valor_repasse_emenda', {numero_br(e("valor_repasse_emenda"))},
            'municipio_nome', {p("munic_proponente")},
            'uf', {p("uf_proponente")},
            'objeto_proposta', {p("objeto_proposta")},
            'situacao_proposta', {p("sit_proposta")}
        )),
        jsonb_build_object(
            'numero_emenda', 'siconv:emenda.NR_EMENDA',
            'parlamentar', 'siconv:emenda.NOME_PARLAMENTAR',
            'tipo_emenda', 'siconv:emenda.TIPO_PARLAMENTAR',
            'valor', 'siconv:emenda.VALOR_REPASSE_EMENDA',
            'municipio_ibge', 'siconv:proposta.COD_MUNIC_IBGE',
            'numero_proposta', 'siconv:proposta.NR_PROPOSTA',
            'ano', 'derivado:proposta.ANO_PROP (a fonte nao publica o ano da emenda)'
        ),
        md5(concat_ws('|', {numero_emenda}, {parlamentar}, {tipo}, {valor}::text, {municipio})),
        now()
    FROM stg_emenda e
    LEFT JOIN stg_proposta p ON p.id_proposta = e.id_proposta
    WHERE nullif(btrim(e.id_proposta), '') IS NOT NULL
      AND nullif(btrim(e.nr_emenda), '') IS NOT NULL
    ORDER BY e.id_proposta, e.nr_emenda, p.nr_proposta NULLS LAST
    ON CONFLICT (fonte, id_externo) DO UPDATE SET
        numero_proposta = EXCLUDED.numero_proposta,
        municipio_ibge  = EXCLUDED.municipio_ibge,
        numero_emenda   = EXCLUDED.numero_emenda,
        ano             = EXCLUDED.ano,
        tipo_emenda     = EXCLUDED.tipo_emenda,
        parlamentar     = EXCLUDED.parlamentar,
        valor           = EXCLUDED.valor,
        detalhe         = EXCLUDED.detalhe,
        proveniencia    = EXCLUDED.proveniencia,
        hash_conteudo   = EXCLUDED.hash_conteudo,
        cache_atualizado_em = EXCLUDED.cache_atualizado_em,
        updated_at      = now()
    """


#: `fonte` das propostas gravadas por esta carga. É o MESMO connector que já lê
#: este arquivo na busca ao vivo (`transferegov_disc`), e isso não é detalhe: a
#: chave do cache é `(fonte, id_externo)` — usar uma fonte própria aqui faria a
#: mesma proposta aparecer DUAS vezes no painel, uma por caminho de ingestão.
FONTE_PROPOSTA = "transferegov_disc"


def sql_upsert_propostas(cols_proposta: list[str], *, ibges: list[str] | None) -> str:
    """`proposta.csv` do pacote → tabela canônica `propostas`.

    É a carga que responde "quero TODAS as propostas do município", sem depender
    de a busca ao vivo varrer 1 GB de CSV a cada filtro do painel (§38). O
    de-para espelha o do connector `transferegov_disc` (§35b): `NR_PROPOSTA` é a
    referência do gestor e a data de criação é REMONTADA de DIA_PROP + MES_PROP
    + ANO_PROP — nunca de uma coluna de vigência, que é outra data.

    `ibges=None` carrega o país inteiro (milhões de linhas); com lista, só o
    território monitorado — o padrão, e a razão de o job caber num Neon.
    """
    p = lambda n: col(cols_proposta, "p", n)  # noqa: E731

    municipio = ibge(p("cod_munic_ibge"))
    numero = texto(p("nr_proposta"), 64)
    objeto = f"nullif(btrim({p('objeto_proposta')}), '')"
    situacao = texto(p("sit_proposta"), 255)
    # VL_GLOBAL_PROP é o valor da PROPOSTA (VL_GLOBAL_CONV seria o do convênio
    # celebrado, que é outro momento do ciclo) — §46.
    global_ = numero_br(p("vl_global_prop"))
    repasse = numero_br(p("vl_repasse_prop"))
    contrapartida = numero_br(p("vl_contrapartida_prop"))
    valor = f"coalesce({global_}, {repasse})"
    criacao = data_componentes(p("dia_prop"), p("mes_prop"), p("ano_prop"), p("dia_proposta"))
    fim_vigencia = data(p("dia_fim_vigencia_proposta"))
    orgao = f"coalesce({texto(p('desc_orgao_sup'), 255)}, {texto(p('desc_orgao'), 255)})"

    # O recorte é o do TERRITÓRIO, e ele entra como filtro da própria varredura:
    # carregar o país e descartar depois custaria a carga inteira em disco.
    onde_municipio = ""
    if ibges is not None:
        lista = ", ".join(f"'{i}'" for i in ibges)
        onde_municipio = f" AND {municipio} IN ({lista})" if lista else " AND false"

    return f"""
    INSERT INTO propostas (
        id, fonte, id_externo, numero_proposta, objeto, orgao_superior, modalidade,
        municipio_ibge, municipio_nome, uf, valor_total, contrapartida, situacao,
        prazos, data_proposta, execucao, dados_fonte, proveniencia,
        hash_conteudo, cache_atualizado_em, excluido_em
    )
    SELECT DISTINCT ON (p.id_proposta)
        gen_random_uuid(),
        '{FONTE_PROPOSTA}',
        left(p.id_proposta, 255),
        {numero},
        {objeto},
        {orgao},
        {texto(p("modalidade"), 64)},
        {municipio},
        {texto(p("munic_proponente"), 255)},
        upper(left(nullif(btrim({p("uf_proponente")}), ''), 2)),
        {valor},
        {contrapartida},
        {situacao},
        CASE WHEN {fim_vigencia} IS NOT NULL THEN jsonb_build_array(jsonb_build_object(
            'tipo', 'fim de vigência',
            'data_limite', to_char({fim_vigencia}, 'YYYY-MM-DD')
        )) END,
        {criacao},
        jsonb_strip_nulls(jsonb_build_object(
            'valor_global', {global_},
            'valor_repasse', {repasse},
            'contrapartida', {contrapartida},
            'ano', {ano(p("ano_prop"))},
            'natureza_juridica', {texto(p("natureza_juridica"), 255)},
            'tipo_transferencia', {texto(p("modalidade"), 64)},
            'ente_recebedor', {texto(p("nm_proponente"), 255)},
            'data_inicio_vigencia', to_char({data(p("dia_inic_vigencia_proposta"))}, 'YYYY-MM-DD'),
            'data_fim_vigencia', to_char({fim_vigencia}, 'YYYY-MM-DD')
        )),
        -- registro-fonte COMPLETO, no MESMO formato que o connector grava
        -- (`plano_acao.csv` = linha bruta): é dele que `ano_de`/`mes_de` e o
        -- "Dados completos da fonte" do detalhe leem (§46).
        jsonb_build_object(
            'plano_acao', jsonb_build_object('csv', to_jsonb(p)),
            'modalidade', {p("modalidade")},
            '_carga', 'siconv:pacote-diario'
        ),
        jsonb_build_object(
            'numero_proposta', 'siconv:proposta.NR_PROPOSTA',
            'data_proposta', 'siconv:proposta.DIA_PROP+MES_PROP+ANO_PROP',
            'valor_total', 'siconv:proposta.VL_GLOBAL_PROP',
            'situacao', 'siconv:proposta.SIT_PROPOSTA',
            'municipio_ibge', 'siconv:proposta.COD_MUNIC_IBGE',
            '_fonte', '{FONTE_PROPOSTA}',
            '_via', 'siconv:pacote-diario'
        ),
        md5(concat_ws('|', {numero}, {situacao}, {valor}::text, {municipio},
                      {criacao}::text, left(coalesce({objeto}, ''), 500))),
        now(),
        NULL  -- a fonte ainda publica esta proposta: uma zeragem anterior é desfeita
    FROM stg_proposta p
    WHERE nullif(btrim(p.id_proposta), '') IS NOT NULL
      AND {municipio} IS NOT NULL{onde_municipio}
    ORDER BY p.id_proposta
    ON CONFLICT (fonte, id_externo) DO UPDATE SET
        numero_proposta = EXCLUDED.numero_proposta,
        objeto          = coalesce(EXCLUDED.objeto, propostas.objeto),
        orgao_superior  = coalesce(EXCLUDED.orgao_superior, propostas.orgao_superior),
        modalidade      = coalesce(EXCLUDED.modalidade, propostas.modalidade),
        municipio_ibge  = EXCLUDED.municipio_ibge,
        municipio_nome  = coalesce(EXCLUDED.municipio_nome, propostas.municipio_nome),
        uf              = coalesce(EXCLUDED.uf, propostas.uf),
        valor_total     = coalesce(EXCLUDED.valor_total, propostas.valor_total),
        contrapartida   = coalesce(EXCLUDED.contrapartida, propostas.contrapartida),
        situacao        = coalesce(EXCLUDED.situacao, propostas.situacao),
        prazos          = coalesce(EXCLUDED.prazos, propostas.prazos),
        data_proposta   = coalesce(EXCLUDED.data_proposta, propostas.data_proposta),
        -- a execução do painel da Visão Geral (empenhado/pago/saldo) é mais
        -- rica que a do CSV: o pacote COMPLETA o que falta, não sobrescreve
        execucao        = coalesce(propostas.execucao, '{{}}'::jsonb) || EXCLUDED.execucao,
        dados_fonte     = coalesce(propostas.dados_fonte, '{{}}'::jsonb) || EXCLUDED.dados_fonte,
        proveniencia    = EXCLUDED.proveniencia,
        hash_conteudo   = EXCLUDED.hash_conteudo,
        cache_atualizado_em = EXCLUDED.cache_atualizado_em,
        excluido_em     = NULL,
        updated_at      = now()
    """


def sql_upsert_empenhos(
    cols_empenho: list[str], cols_convenio: list[str], cols_proposta: list[str]
) -> str:
    """Empenhos do SIconv → `proposta_empenhos`.

    O empenho só conhece `NR_CONVENIO`; quem sabe de que proposta (e portanto de
    que MUNICÍPIO) ele é, é o convênio. Por isso a cadeia tem três arquivos —
    empenho → convenio → proposta. Empenho de convênio que não veio no pacote
    entra sem território em vez de sumir: o documento existe.

    `valor_pago`/`valor_liquidado` ficam NULL de propósito: o pacote publica
    pagamento por CONVÊNIO, não por empenho. Ratear seria inventar.
    """
    emp = lambda n: col(cols_empenho, "e", n)  # noqa: E731
    conv = lambda n: col(cols_convenio, "c", n)  # noqa: E731
    prop = lambda n: col(cols_proposta, "p", n)  # noqa: E731

    numero = texto(emp("nr_empenho"), 64)
    valor = numero_br(emp("valor_empenho"))
    municipio = ibge(prop("cod_munic_ibge"))
    emissao = data(emp("data_emissao"))

    return f"""
    INSERT INTO proposta_empenhos (
        id, fonte, id_externo, numero_proposta, municipio_ibge,
        numero_empenho, data_empenho, tipo_empenho, situacao, ano,
        valor_empenhado, ug_emitente, natureza_despesa, fonte_recurso,
        programa_trabalho, observacao,
        detalhe, proveniencia, hash_conteudo, cache_atualizado_em
    )
    SELECT DISTINCT ON (e.id_empenho)
        gen_random_uuid(),
        '{FONTE}',
        left(e.id_empenho, 128),
        {texto(prop("nr_proposta"), 64)},
        {municipio},
        {numero},
        {emissao},
        {texto(emp("desc_tipo_nota"), 64)},
        {texto(emp("desc_situacao_empenho"), 128)},
        left(nullif(to_char({emissao}, 'YYYY'), ''), 4),
        {valor},
        {texto(emp("ug_emitente"), 255)},
        {texto(emp("natureza_despesa"), 255)},
        {texto(emp("fonte_recurso"), 255)},
        {texto(emp("plano_interno"), 255)},
        nullif(btrim({emp("observacao_empenho")}), ''),
        jsonb_strip_nulls(jsonb_build_object(
            'nr_convenio', e.nr_convenio,
            'id_proposta', {conv("id_proposta")},
            'ptres', {emp("ptres")},
            'tipo_nota', {emp("tipo_nota")},
            'ug_responsavel', {emp("ug_responsavel")},
            'resultado_primario', {emp("resultado_primario")},
            'descricao_emenda_siafi', {emp("descricao_emenda_siafi")},
            'municipio_nome', {prop("munic_proponente")},
            'uf', {prop("uf_proponente")}
        )),
        jsonb_build_object(
            'numero_empenho', 'siconv:empenho.NR_EMPENHO',
            'valor_empenhado', 'siconv:empenho.VALOR_EMPENHO',
            'data_empenho', 'siconv:empenho.DATA_EMISSAO',
            'municipio_ibge', 'siconv:proposta.COD_MUNIC_IBGE (via convenio.NR_CONVENIO)',
            'valor_pago', 'ausente:o pacote publica pagamento por convenio, nao por empenho'
        ),
        md5(concat_ws('|', {numero}, {valor}::text, {emissao}::text, {municipio})),
        now()
    FROM stg_empenho e
    LEFT JOIN stg_convenio c ON c.nr_convenio = e.nr_convenio
    LEFT JOIN stg_proposta p ON p.id_proposta = c.id_proposta
    WHERE nullif(btrim(e.id_empenho), '') IS NOT NULL
    ORDER BY e.id_empenho, c.nr_convenio NULLS LAST
    ON CONFLICT (fonte, id_externo) DO UPDATE SET
        numero_proposta   = EXCLUDED.numero_proposta,
        municipio_ibge    = EXCLUDED.municipio_ibge,
        numero_empenho    = EXCLUDED.numero_empenho,
        data_empenho      = EXCLUDED.data_empenho,
        tipo_empenho      = EXCLUDED.tipo_empenho,
        situacao          = EXCLUDED.situacao,
        ano               = EXCLUDED.ano,
        valor_empenhado   = EXCLUDED.valor_empenhado,
        ug_emitente       = EXCLUDED.ug_emitente,
        natureza_despesa  = EXCLUDED.natureza_despesa,
        fonte_recurso     = EXCLUDED.fonte_recurso,
        programa_trabalho = EXCLUDED.programa_trabalho,
        observacao        = EXCLUDED.observacao,
        detalhe           = EXCLUDED.detalhe,
        proveniencia      = EXCLUDED.proveniencia,
        hash_conteudo     = EXCLUDED.hash_conteudo,
        cache_atualizado_em = EXCLUDED.cache_atualizado_em,
        updated_at        = now()
    """


# --------------------------------------------------------------------------
# orquestração
# --------------------------------------------------------------------------


async def aplicar_carga(conn: AsyncConnection, arquivos: dict[str, Path]) -> dict[str, int]:
    """Staging + upserts numa transação. Devolve o que foi gravado por entidade.

    Só roda o upsert cujos arquivos estão presentes: baixar menos tabelas
    (`SICONV_TABELAS`) degrada o escopo da carga, não a quebra.

    Liga `app.plataforma` ANTES do upsert e isso não é detalhe: `INSERT … ON
    CONFLICT DO UPDATE` aplica a policy de **SELECT** sobre a linha nova (o
    Postgres pode precisar lê-la), e a de `proposta_emendas` recorta por
    `municipios_interesse`. Sem a bandeira, este job — que é global e não tem
    tenant — via TODA linha com município preenchido recusada com "new row
    violates row-level security policy", e nenhuma emenda entrava. A bandeira é
    a mesma que `demandas` usa para a fila cross-tenant da assessoria.
    """
    await conn.execute(text("SELECT set_config('app.plataforma', 'on', true)"))
    colunas = {t: await carregar_staging(conn, t, caminho) for t, caminho in arquivos.items()}

    gravadas: dict[str, int] = {}

    if {"emenda", "proposta"} <= colunas.keys():
        resultado = await conn.execute(
            text(sql_upsert_emendas(colunas["emenda"], colunas["proposta"]))
        )
        gravadas["emendas"] = resultado.rowcount or 0

    if "proposta" in colunas:
        escopo = await escopo_propostas()
        ibges = None if escopo == ESCOPO_NACIONAL else await ibges_do_territorio(conn)
        if ibges is not None and not ibges:
            # Nenhum município monitorado ainda (instalação nova): não há o que
            # carregar, e dizer isso é melhor que gravar o país inteiro "por
            # via das dúvidas".
            log.warning("siconv: nenhum município em municipios_interesse — propostas puladas")
            gravadas["propostas"] = 0
        else:
            log.info(
                "siconv: carregando propostas (escopo=%s, %s)",
                escopo,
                "país inteiro" if ibges is None else f"{len(ibges)} município(s)",
            )
            resultado = await conn.execute(
                text(sql_upsert_propostas(colunas["proposta"], ibges=ibges))
            )
            gravadas["propostas"] = resultado.rowcount or 0

    if {"empenho", "convenio", "proposta"} <= colunas.keys():
        resultado = await conn.execute(
            text(sql_upsert_empenhos(colunas["empenho"], colunas["convenio"], colunas["proposta"]))
        )
        gravadas["empenhos"] = resultado.rowcount or 0

    return gravadas


async def _registrar(
    conn: AsyncConnection, inicio: datetime, status: str, registros: int, erro: str | None
) -> None:
    """Incidente/execução em `sync_runs` — erro de fonte nunca é engolido (§10)."""
    await conn.execute(
        text(
            "INSERT INTO sync_runs "
            "(id, fonte, tipo, status, registros, iniciado_em, finalizado_em, erro) "
            "VALUES (gen_random_uuid(), :f, 'agendado', :s, :r, :i, now(), :e)"
        ),
        {
            "f": FONTE,
            "s": status,
            "r": registros,
            "i": inicio,
            "e": erro[:2000] if erro else None,
        },
    )


async def executar(dir_trabalho: str | None = None, tabelas: tuple[str, ...] | None = None) -> dict:
    """Uma carga completa: baixa → descompacta → COPY → upsert. Devolve o resumo.

    `tabelas` restringe o lote (é o que a rota admin manda quando o operador
    pede só `proposta`, por exemplo); vazio = o recorte de `tabelas_alvo()`.
    Tabela fora do catálogo é ignorada em vez de derrubar a carga.
    """
    inicio = datetime.now(UTC)
    base_dir = Path(dir_trabalho) if dir_trabalho else None
    tmp = None if base_dir else tempfile.TemporaryDirectory(prefix="siconv-")
    destino = base_dir or Path(tmp.name)  # type: ignore[union-attr]
    alvo = tuple(t for t in (tabelas or tabelas_alvo()) if t in siconv_downloads.ARQUIVOS)

    try:
        arquivos: dict[str, Path] = {}
        for tabela in alvo:
            log.info("siconv: baixando %s…", tabela)
            arquivos[tabela] = await siconv_downloads.baixar_csv(tabela, destino)

        async with engine.begin() as conn:
            gravadas = await aplicar_carga(conn, arquivos)
            await _registrar(conn, inicio, "ok", sum(gravadas.values()), None)

        dur = (datetime.now(UTC) - inicio).total_seconds()
        resumo = ", ".join(f"{v} {k}" for k, v in gravadas.items()) or "nada"
        log.info("siconv: carga concluída — %s em %.0fs", resumo, dur)
        return {"status": "ok", "segundos": dur, **gravadas}

    except Exception as exc:  # noqa: BLE001 — a falha vira registro, não silêncio
        log.exception("siconv: carga falhou")
        try:
            async with engine.begin() as conn:
                await _registrar(conn, inicio, "erro", 0, f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001 — banco fora do ar: só o log resta
            log.warning("siconv: não consegui registrar o incidente em sync_runs")
        return {"status": "erro", "erro": str(exc)}
    finally:
        if tmp is not None:
            tmp.cleanup()


async def sweep(tabelas: tuple[str, ...] | None = None) -> dict:
    """`executar` sob advisory lock — só uma réplica carrega por vez."""
    async with engine.connect() as conn:
        travou = (
            await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})
        ).scalar()
        if not travou:
            log.warning("siconv: outra carga em andamento — pulando")
            return {"status": "ocupado"}
        try:
            return await executar(tabelas=tabelas)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})


def _segundos_ate_proxima_execucao(agora: datetime) -> float:
    alvo = agora.replace(hour=HORA_UTC, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def loop() -> None:
    if not ATIVO:
        log.warning("siconv: carga diária desativada por SICONV_DIARIO_ATIVO")
        return
    log.info("siconv: carga agendada para %02d:00 UTC", HORA_UTC)
    while True:
        espera = _segundos_ate_proxima_execucao(datetime.now(UTC))
        log.info("siconv: próxima carga em %.0f min", espera / 60)
        await asyncio.sleep(espera)
        try:
            await sweep()
        except Exception:
            # O loop nunca morre: uma carga ruim não pode encerrar o agendador
            # e congelar as emendas até alguém reiniciar o container.
            log.exception("siconv: carga falhou")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # RODAR_AGORA=1 força uma carga imediata e sai — primeira carga e testes,
    # sem esperar a janela agendada.
    if os.getenv("RODAR_AGORA") == "1":
        asyncio.run(sweep())
    else:
        asyncio.run(loop())
