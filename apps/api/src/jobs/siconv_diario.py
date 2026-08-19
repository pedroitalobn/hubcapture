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

log = logging.getLogger(__name__)

FONTE = "siconv"

HORA_UTC = int(os.getenv("SICONV_DIARIO_HORA_UTC", "7"))
ATIVO = os.getenv("SICONV_DIARIO_ATIVO", "1") not in ("0", "false", "False")
# Trava global: duas réplicas do worker carregariam as MESMAS linhas em
# paralelo e disputariam o upsert. Advisory lock cai sozinha se o processo
# morrer — flag em tabela deixaria trava órfã.
LOCK_ID = 8_140_233_902


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


def numero(expr: str) -> str:
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

    assinado = numero(e("valor_repasse_emenda"))
    cadastrado = numero(e("valor_repasse_proposta_emenda"))
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
        {texto(p('nr_proposta'), 64)},
        {municipio},
        {numero_emenda},
        {ano(p('ano_prop'))},
        {tipo},
        {parlamentar},
        {valor},
        jsonb_strip_nulls(jsonb_build_object(
            'id_proposta', e.id_proposta,
            'cod_programa_emenda', {e('cod_programa_emenda')},
            'beneficiario_emenda', {e('beneficiario_emenda')},
            'qualif_proponente', {e('qualif_proponente')},
            'ind_impositivo', {e('ind_impositivo')},
            'valor_repasse_proposta_emenda', {numero(e('valor_repasse_proposta_emenda'))},
            'valor_repasse_emenda', {numero(e('valor_repasse_emenda'))},
            'municipio_nome', {p('munic_proponente')},
            'uf', {p('uf_proponente')},
            'objeto_proposta', {p('objeto_proposta')},
            'situacao_proposta', {p('sit_proposta')}
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


# --------------------------------------------------------------------------
# orquestração
# --------------------------------------------------------------------------


async def aplicar_carga(conn: AsyncConnection, arquivos: dict[str, Path]) -> int:
    """Staging + upsert numa transação. Devolve quantas emendas foram gravadas.

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
    resultado = await conn.execute(text(sql_upsert_emendas(colunas["emenda"], colunas["proposta"])))
    return resultado.rowcount or 0


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


async def executar(dir_trabalho: str | None = None) -> dict:
    """Uma carga completa: baixa → descompacta → COPY → upsert. Devolve o resumo."""
    inicio = datetime.now(UTC)
    base_dir = Path(dir_trabalho) if dir_trabalho else None
    tmp = None if base_dir else tempfile.TemporaryDirectory(prefix="siconv-")
    destino = base_dir or Path(tmp.name)  # type: ignore[union-attr]

    try:
        arquivos: dict[str, Path] = {}
        for tabela in CARREGADAS:
            log.info("siconv: baixando %s…", tabela)
            arquivos[tabela] = await siconv_downloads.baixar_csv(tabela, destino)

        async with engine.begin() as conn:
            gravadas = await aplicar_carga(conn, arquivos)
            await _registrar(conn, inicio, "ok", gravadas, None)

        dur = (datetime.now(UTC) - inicio).total_seconds()
        log.info("siconv: carga concluída — %d emenda(s) gravadas em %.0fs", gravadas, dur)
        return {"status": "ok", "emendas": gravadas, "segundos": dur}

    except Exception as exc:  # noqa: BLE001 — a falha vira registro, não silêncio
        log.exception("siconv: carga falhou")
        try:
            async with engine.begin() as conn:
                await _registrar(conn, inicio, "erro", 0, f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001 — banco fora do ar: só o log resta
            log.warning("siconv: não consegui registrar o incidente em sync_runs")
        return {"status": "erro", "emendas": 0, "erro": str(exc)}
    finally:
        if tmp is not None:
            tmp.cleanup()


async def sweep() -> dict:
    """`executar` sob advisory lock — só uma réplica carrega por vez."""
    async with engine.connect() as conn:
        travou = (
            await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})
        ).scalar()
        if not travou:
            log.warning("siconv: outra carga em andamento — pulando")
            return {"status": "ocupado", "emendas": 0}
        try:
            return await executar()
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
