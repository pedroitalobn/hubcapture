"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import Proposta
from ..schemas.proposta import (
    AnoResumo,
    PropostaCanonica,
    PropostaRead,
    PropostasResumo,
)

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
    "titulo",
    "objeto",
    "descricao",
    "orgao_superior",
    "modalidade",
    "ano",
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "valor_total",
    "contrapartida",
    "situacao",
    "emenda",
    "prazos",
    "pendencias",
    "movimentacao",
    "data_atualizacao_fonte",
    "url_origem",
    "proveniencia",
    "execucao",
    "hash_conteudo",
)


# Eixo "QUE TIPO?" da jornada: uma proposta CADASTRADA já existe no sistema do
# governo (convênio/plano em andamento); DISPONÍVEL é oportunidade aberta
# (edital/programa recebendo propostas). Derivado da situação — de-para por
# palavra-chave, sem coluna nova (calibrável aqui).
_KW_DISPONIVEL = ("dispon", "divulga", "abert", "public", "recebendo", "edital")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def classificar_tipo(situacao: str | None) -> str:
    """'disponivel' (oportunidade aberta) ou 'cadastrada' (proposta existente)."""
    if not situacao:
        return "cadastrada"
    norm = _sem_acento(situacao).lower()
    return "disponivel" if any(kw in norm for kw in _KW_DISPONIVEL) else "cadastrada"


async def listar(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    area: str | None = None,
    valor_min: Decimal | None = None,
    valor_max: Decimal | None = None,
    tipo: str | None = None,
    ano: int | None = None,
) -> list[Proposta]:
    stmt = select(Proposta)
    if municipio:
        stmt = stmt.where(Proposta.municipio_ibge == municipio)
    if fonte:
        stmt = stmt.where(Proposta.fonte == fonte)
    if situacao:
        stmt = stmt.where(Proposta.situacao == situacao)
    if ano is not None:
        stmt = stmt.where(Proposta.ano == ano)
    if area:
        from .perfil import AREA_FONTES

        fontes_area = AREA_FONTES.get(area)
        if fontes_area:
            stmt = stmt.where(Proposta.fonte.in_(fontes_area))
    if valor_min is not None:
        stmt = stmt.where(Proposta.valor_total >= valor_min)
    if valor_max is not None:
        stmt = stmt.where(Proposta.valor_total <= valor_max)
    stmt = stmt.order_by(
        Proposta.ano.desc().nullslast(), Proposta.cache_atualizado_em.desc().nullslast()
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if tipo in ("cadastrada", "disponivel"):
        rows = [p for p in rows if classificar_tipo(p.situacao) == tipo]
    return rows


async def resumo(
    session: AsyncSession,
    *,
    municipio: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    area: str | None = None,
    tipo: str | None = None,
    ano: int | None = None,
) -> PropostasResumo:
    """KPIs do exercício em foco + a quebra por ano que alimenta o filtro.

    `por_ano` é calculado SEM o recorte de ano — senão o filtro esconderia os
    outros exercícios que ele mesmo precisa oferecer.
    """
    todas = await listar(
        session, municipio=municipio, fonte=fonte, situacao=situacao, area=area, tipo=tipo
    )

    por_ano_itens: dict[int | None, list[Proposta]] = defaultdict(list)
    for p in todas:
        por_ano_itens[p.ano].append(p)

    por_ano = [
        AnoResumo(
            ano=a,
            total=len(itens),
            valor_total=sum((p.valor_total or Decimal(0) for p in itens), Decimal(0)),
        )
        # exercícios mais recentes primeiro; os sem ano ficam no fim
        for a, itens in sorted(por_ano_itens.items(), key=lambda kv: (kv[0] is None, -(kv[0] or 0)))
    ]

    foco = todas if ano is None else por_ano_itens.get(ano, [])
    return PropostasResumo(
        ano=ano,
        total=len(foco),
        valor_total=sum((p.valor_total or Decimal(0) for p in foco), Decimal(0)),
        contrapartida_total=sum((p.contrapartida or Decimal(0) for p in foco), Decimal(0)),
        municipios=len({p.municipio_ibge for p in foco if p.municipio_ibge}),
        por_ano=por_ano,
        propostas=[PropostaRead.model_validate(p) for p in foco],
    )


def _prazos_na_janela(p: Proposta, inicio: date, fim: date) -> list[dict]:
    """Prazos da proposta (jsonb [{tipo, data_limite}]) dentro da janela."""
    dentro = []
    for prazo in p.prazos or []:
        bruto = (prazo or {}).get("data_limite")
        try:
            data_limite = date.fromisoformat(str(bruto)[:10])
        except (TypeError, ValueError):
            continue
        if inicio <= data_limite <= fim:
            dentro.append({**prazo, "data_limite": data_limite.isoformat()})
    return dentro


async def listar_por_prazo(
    session: AsyncSession, *, dias: int = 30
) -> list[tuple[Proposta, list[dict]]]:
    """Propostas com prazo vencendo na janela [hoje, hoje+dias] — consulta
    estruturada (não-RAG) que alimenta o painel e a resposta do chat."""
    hoje = date.today()
    fim = hoje + timedelta(days=dias)
    stmt = select(Proposta).where(Proposta.prazos.isnot(None))
    rows = (await session.execute(stmt)).scalars().all()
    com_prazo = []
    for p in rows:
        na_janela = _prazos_na_janela(p, hoje, fim)
        if na_janela:
            com_prazo.append((p, na_janela))
    com_prazo.sort(key=lambda item: min(pr["data_limite"] for pr in item[1]))
    return com_prazo


async def obter(session: AsyncSession, proposta_id: uuid.UUID) -> Proposta | None:
    result = await session.execute(select(Proposta).where(Proposta.id == proposta_id))
    return result.scalar_one_or_none()


async def upsert(session: AsyncSession, canonica: PropostaCanonica) -> None:
    """Insere/atualiza uma proposta pelo par único (fonte, id_externo)."""
    now = datetime.now(UTC)
    values = canonica.model_dump()
    values["cache_atualizado_em"] = now

    stmt = pg_insert(Proposta).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    stmt = stmt.on_conflict_do_update(
        constraint="uq_propostas_fonte_id_externo",
        set_=update_set,
    )
    await session.execute(stmt)
