"""Serviço de repasses (recebidos) — cache-first, upsert, visão geral e sync.

Espelha o padrão de `services/propostas.py`. Leitura sempre do cache (RLS isola
por município); o fetch ao vivo (sync) usa os connectors + normalize_repasse.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.base import get_connector
from ..ingestion.normalizer_repasse import normalize_repasse
from ..models.audit_log import AuditLog
from ..models.municipio_interesse import MunicipioInteresse
from ..models.repasse import Repasse
from ..schemas.repasse import (
    DistribuicaoItem,
    EmendaItem,
    FonteResumo,
    OpcoesEmendas,
    RankingParlamentar,
    RepasseCanonico,
    RepasseRead,
    RepassesPorDia,
    ResumoEmendas,
    SerieAnoEmendas,
    VisaoGeral,
)
from . import municipios
from ._sync import registrar_sync
from ._territorio import Municipios
from ._territorio import filtrar as filtrar_municipio

_UPSERT_FIELDS = (
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "data_repasse",
    "competencia",
    "descricao",
    "categoria",
    "orgao_superior",
    "natureza",
    "valor",
    "documento",
    "emenda",
    "detalhe",
    "proveniencia",
    "hash_conteudo",
)


def _signed(valor: Decimal | None, natureza: str | None) -> Decimal:
    """Dedução entra negativa; crédito/repasse positivo (líquido do FPM)."""
    if valor is None:
        return Decimal(0)
    return -valor if natureza == "deducao" else valor


async def listar(
    session: AsyncSession,
    *,
    municipio: Municipios = None,
    fonte: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    emenda: bool | None = None,
    orgao: str | None = None,
    categoria: str | None = None,
    q: str | None = None,
) -> list[Repasse]:
    stmt = select(Repasse)
    # um município, vários (recorte do painel) ou nenhum (todo o território)
    stmt = filtrar_municipio(stmt, Repasse.municipio_ibge, municipio)
    if fonte:
        stmt = stmt.where(Repasse.fonte == fonte)
    # Janela por data — mas lançamento SEM data não pode ser excluído pelo
    # filtro: o FNS publica o agregado do EXERCÍCIO (sem OB, sem dia) e ficava
    # fora até dos cards de total por fonte, como se a fonte não tivesse
    # trazido nada. Quando ele tem competência, ela decide se cabe na janela;
    # sem competência alguma, entra (é melhor mostrar com "sem data" do que
    # esconder dinheiro que a fonte publicou).
    if inicio:
        stmt = stmt.where(
            or_(
                Repasse.data_repasse >= inicio,
                and_(
                    Repasse.data_repasse.is_(None),
                    or_(
                        Repasse.competencia.is_(None),
                        Repasse.competencia >= str(inicio.year),
                    ),
                ),
            )
        )
    if fim:
        stmt = stmt.where(
            or_(
                Repasse.data_repasse <= fim,
                and_(
                    Repasse.data_repasse.is_(None),
                    or_(
                        Repasse.competencia.is_(None),
                        Repasse.competencia <= str(fim.year),
                    ),
                ),
            )
        )
    if emenda is not None:
        stmt = stmt.where(Repasse.emenda.is_(emenda))
    if orgao:
        stmt = stmt.where(Repasse.orgao_superior == orgao)
    if categoria:
        stmt = stmt.where(Repasse.categoria == categoria)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Repasse.descricao.ilike(like),
                Repasse.categoria.ilike(like),
                Repasse.orgao_superior.ilike(like),
                Repasse.documento.ilike(like),
                Repasse.id_externo.ilike(like),
            )
        )
    stmt = stmt.order_by(Repasse.data_repasse.desc().nullslast())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert(session: AsyncSession, canonico: RepasseCanonico) -> None:
    now = datetime.now(UTC)
    values = canonico.model_dump()
    values["cache_atualizado_em"] = now
    stmt = pg_insert(Repasse).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(constraint="uq_repasses_fonte_id_externo", set_=update_set)
    await session.execute(stmt)


async def visao_geral(
    session: AsyncSession,
    *,
    municipio: Municipios = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> VisaoGeral:
    """Painel consolidado: KPI de total pago, cards por fonte e feed por data."""
    rows = await listar(session, municipio=municipio, inicio=inicio, fim=fim)

    total = Decimal(0)
    por_fonte_total: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    por_fonte_qtd: dict[str, int] = defaultdict(int)
    por_dia: dict[date, list[Repasse]] = defaultdict(list)
    # lançamentos SEM data do pagamento (o FNS publica o agregado do
    # exercício): agrupados pela competência, para não sumirem do feed
    por_exercicio: dict[str, list[Repasse]] = defaultdict(list)

    for r in rows:
        s = _signed(r.valor, r.natureza)
        total += s
        por_fonte_total[r.fonte] += s
        por_fonte_qtd[r.fonte] += 1
        if r.data_repasse is not None:
            por_dia[r.data_repasse].append(r)
        else:
            por_exercicio[str(r.competencia or "sem competência")].append(r)

    fontes = [
        FonteResumo(fonte=f, total=por_fonte_total[f], movimentacoes=por_fonte_qtd[f])
        for f in sorted(por_fonte_total, key=lambda x: por_fonte_total[x], reverse=True)
    ]
    # o feed identifica cada lançamento pelo município (nome), não pelo código
    mapa = await municipios.mapa_territorio(session)
    feed = [
        RepassesPorDia(
            data=d,
            subtotal=sum((_signed(r.valor, r.natureza) for r in por_dia[d]), Decimal(0)),
            itens=await municipios.enriquecer(
                session, [RepasseRead.model_validate(r) for r in por_dia[d]], mapa=mapa
            ),
        )
        for d in sorted(por_dia, reverse=True)
    ]
    # os grupos por exercício entram DEPOIS dos datados: quem tem dia é mais
    # específico e responde "o que caiu esta semana"; o agregado do ano é
    # contexto, não novidade
    feed += [
        RepassesPorDia(
            data=None,
            competencia=comp,
            subtotal=sum((_signed(r.valor, r.natureza) for r in por_exercicio[comp]), Decimal(0)),
            itens=await municipios.enriquecer(
                session,
                [RepasseRead.model_validate(r) for r in por_exercicio[comp]],
                mapa=mapa,
            ),
        )
        for comp in sorted(por_exercicio, reverse=True)
    ]
    return VisaoGeral(
        total_pago=total,
        movimentacoes=len(rows),
        inicio=inicio,
        fim=fim,
        fontes=fontes,
        feed=feed,
    )


# ── Emendas parlamentares ───────────────────────────────────────────────────
# A gestão de emendas é uma LENTE sobre os repasses com `emenda=True`: o que os
# parlamentares destinaram ao município, quanto foi empenhado × pago, por ano,
# modalidade (individual/bancada/comissão) e área (função orçamentária).


def _detalhe(r: Repasse) -> dict:
    return r.detalhe if isinstance(r.detalhe, dict) else {}


def _dec(v) -> Decimal:
    if v in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(v))
    except (ArithmeticError, ValueError):
        return Decimal(0)


def parlamentar_de(r: Repasse) -> str | None:
    d = _detalhe(r)
    return d.get("parlamentar") or d.get("autor")


def modalidade_de(r: Repasse) -> str | None:
    return _detalhe(r).get("modalidade")


def ano_de(r: Repasse) -> str | None:
    d = _detalhe(r)
    if d.get("ano"):
        return str(d["ano"])[:4]
    if r.data_repasse:
        return str(r.data_repasse.year)
    if r.competencia:
        return str(r.competencia)[:4]
    return None


def _empenhado(r: Repasse) -> Decimal:
    """Empenhado informado pela fonte; sem ele, o próprio valor do repasse."""
    return _dec(_detalhe(r).get("valor_empenhado")) or _dec(r.valor)


def _pago(r: Repasse) -> Decimal:
    return _dec(_detalhe(r).get("valor_pago")) or _dec(r.valor)


def _pct(pago: Decimal, empenhado: Decimal) -> float:
    return float(pago / empenhado * 100) if empenhado else 0.0


def _emenda_item(r: Repasse) -> EmendaItem:
    emp, pg = _empenhado(r), _pago(r)
    d = _detalhe(r)
    return EmendaItem(
        id=r.id,
        codigo=str(d.get("codigo_emenda") or r.id_externo),
        numero=r.documento,
        parlamentar=parlamentar_de(r),
        partido=d.get("partido"),
        modalidade=modalidade_de(r),
        area=r.categoria or d.get("funcao"),
        orgao_superior=r.orgao_superior,
        ano=ano_de(r),
        empenhado=emp,
        pago=pg,
        percentual_executado=_pct(pg, emp),
        data_repasse=r.data_repasse,
        descricao=r.descricao,
        municipio_nome=r.municipio_nome,
        uf=r.uf,
    )


async def listar_emendas(
    session: AsyncSession,
    *,
    municipio: Municipios = None,
    inicio: date | None = None,
    fim: date | None = None,
    orgao: str | None = None,
    q: str | None = None,
    ano: str | None = None,
    modalidade: str | None = None,
    parlamentar: str | None = None,
) -> list[Repasse]:
    """Repasses de emenda do território, já com os filtros da tela aplicados.

    Ano/modalidade/parlamentar vivem no jsonb `detalhe` → filtro em Python (o
    recorte já é do município pelo RLS, então o conjunto é pequeno)."""
    rows = await listar(
        session, municipio=municipio, inicio=inicio, fim=fim, emenda=True, orgao=orgao, q=q
    )
    if ano:
        rows = [r for r in rows if ano_de(r) == str(ano)]
    if modalidade:
        rows = [r for r in rows if modalidade_de(r) == modalidade]
    if parlamentar:
        rows = [r for r in rows if parlamentar_de(r) == parlamentar]
    return rows


async def resumo_emendas(session: AsyncSession, **filtros) -> ResumoEmendas:
    """Cards empenhado/pago, evolução anual, distribuições, ranking e lista."""
    rows = await listar_emendas(session, **filtros)
    # as opções dos filtros vêm do universo do território (sem os filtros de
    # emenda aplicados), senão escolher um parlamentar esvaziaria o dropdown
    universo = await listar_emendas(
        session,
        municipio=filtros.get("municipio"),
        inicio=filtros.get("inicio"),
        fim=filtros.get("fim"),
    )

    empenhado = sum((_empenhado(r) for r in rows), Decimal(0))
    pago = sum((_pago(r) for r in rows), Decimal(0))

    por_ano: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    por_modalidade: dict[str, list] = defaultdict(lambda: [Decimal(0), 0])
    por_area: dict[str, list] = defaultdict(lambda: [Decimal(0), 0])
    ranking: dict[str, dict] = {}

    for r in rows:
        emp, pg = _empenhado(r), _pago(r)
        ano = ano_de(r)
        if ano:
            por_ano[ano][0] += emp
            por_ano[ano][1] += pg
        mod = modalidade_de(r) or "não informada"
        por_modalidade[mod][0] += pg
        por_modalidade[mod][1] += 1
        area = r.categoria or _detalhe(r).get("funcao") or "não informada"
        por_area[area][0] += pg
        por_area[area][1] += 1
        nome = parlamentar_de(r)
        if nome:
            acc = ranking.setdefault(
                nome,
                {
                    "parlamentar": nome,
                    "partido": _detalhe(r).get("partido"),
                    "empenhado": Decimal(0),
                    "pago": Decimal(0),
                    "emendas": 0,
                },
            )
            acc["empenhado"] += emp
            acc["pago"] += pg
            acc["emendas"] += 1

    def _ordenado(valores: set[str | None]) -> list[str]:
        return sorted(v for v in valores if v)

    return ResumoEmendas(
        empenhado=empenhado,
        pago=pago,
        percentual_executado=_pct(pago, empenhado),
        emendas=len(rows),
        por_ano=[
            SerieAnoEmendas(ano=a, empenhado=v[0], pago=v[1]) for a, v in sorted(por_ano.items())
        ],
        por_modalidade=[
            DistribuicaoItem(chave=k, valor=v[0], quantidade=v[1])
            for k, v in sorted(por_modalidade.items(), key=lambda kv: -kv[1][0])
        ],
        por_area=[
            DistribuicaoItem(chave=k, valor=v[0], quantidade=v[1])
            for k, v in sorted(por_area.items(), key=lambda kv: -kv[1][0])
        ],
        ranking_parlamentares=[
            RankingParlamentar(**acc) for acc in sorted(ranking.values(), key=lambda a: -a["pago"])
        ],
        itens=[_emenda_item(r) for r in rows],
        opcoes=OpcoesEmendas(
            anos=sorted({a for a in (ano_de(r) for r in universo) if a}, reverse=True),
            modalidades=_ordenado({modalidade_de(r) for r in universo}),
            parlamentares=_ordenado({parlamentar_de(r) for r in universo}),
            orgaos=_ordenado({r.orgao_superior for r in universo}),
        ),
    )


_COLUNAS_EMENDAS = (
    "codigo",
    "numero",
    "parlamentar",
    "partido",
    "modalidade",
    "area",
    "orgao",
    "ano",
    "empenhado",
    "pago",
    "percentual_executado",
    "data_repasse",
    "municipio",
    "uf",
    "descricao",
)


def gerar_csv_emendas(rows: list[Repasse]) -> str:
    """Exportação da lista de emendas (CSV ';', abre no Excel)."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_COLUNAS_EMENDAS, delimiter=";")
    writer.writeheader()
    for r in rows:
        item = _emenda_item(r)
        writer.writerow(
            {
                "codigo": item.codigo,
                "numero": item.numero or "",
                "parlamentar": item.parlamentar or "",
                "partido": item.partido or "",
                "modalidade": item.modalidade or "",
                "area": item.area or "",
                "orgao": item.orgao_superior or "",
                "ano": item.ano or "",
                "empenhado": item.empenhado,
                "pago": item.pago,
                "percentual_executado": f"{item.percentual_executado:.1f}",
                "data_repasse": item.data_repasse.isoformat() if item.data_repasse else "",
                "municipio": item.municipio_nome or "",
                "uf": item.uf or "",
                "descricao": item.descricao or "",
            }
        )
    return buffer.getvalue()


async def sync_municipio(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    municipio_ibge: str,
    fontes: list[str],
) -> int:
    """Fetch ao vivo dos recebidos de um município para as fontes dadas.

    Garante `municipios_interesse` (senão o RLS esconde o resultado), grava
    audit_log e registra cada fonte em sync_runs. Retorna o total gravado.
    """
    stmt = (
        pg_insert(MunicipioInteresse)
        .values(usuario_id=usuario_id, ibge=municipio_ibge, modo="avulso")
        .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
    )
    await session.execute(stmt)
    session.add(
        AuditLog(
            usuario_id=usuario_id,
            acao="sync_repasses",
            entidade=f"{','.join(fontes)}:{municipio_ibge}",
        )
    )

    total = 0
    for fonte in fontes:
        iniciado = datetime.now(UTC)
        try:
            connector = get_connector(fonte)
            registros = await connector.collect(
                municipio_ibge,
                since=await _since_para(session, fonte, municipio_ibge),
            )
            n = 0
            for record in registros:
                await upsert(session, normalize_repasse(record))
                n += 1
            total += n
        except Exception as exc:  # nunca engolir: registra incidente e propaga
            await registrar_sync(
                usuario_id=usuario_id,
                fonte=fonte,
                tipo="avulso",
                status="erro",
                registros=0,
                iniciado_em=iniciado,
                finalizado_em=datetime.now(UTC),
                erro=f"{type(exc).__name__}: {exc}"[:2000],
            )
            raise
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=fonte,
            tipo="avulso",
            status="ok",
            registros=n,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
        )
    return total


def _since() -> date:
    return date(date.today().year, 1, 1)


#: profundidade da PRIMEIRA coleta de um município — os exercícios "antigos"
#: que o gestor espera encontrar ao entrar (3 anos é o teto dos connectors)
ANOS_PRIMEIRA_COLETA = 3


async def _since_para(session: AsyncSession, fonte: str, municipio_ibge: str) -> date:
    """Janela da coleta: primeira vez = histórico; as demais = exercício atual.

    O modelo é por demanda: o município entra quando um usuário o escolhe, e a
    PRIMEIRA coleta puxa os exercícios anteriores de uma vez (o gestor abre a
    tela esperando ver o histórico, não só o ano corrente). Depois disso o
    cron diário só atualiza o exercício atual — recoletar 3 anos todo dia
    triplicaria o custo do egresso sem fato novo (exercício fechado não muda).
    """
    ja_tem = (
        await session.execute(
            select(Repasse.id)
            .where(Repasse.fonte == fonte, Repasse.municipio_ibge == municipio_ibge)
            .limit(1)
        )
    ).first()
    if ja_tem:
        return _since()
    return date(date.today().year - (ANOS_PRIMEIRA_COLETA - 1), 1, 1)
