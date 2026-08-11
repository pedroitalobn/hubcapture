"""Ordem do painel — "recentes" é a data da PROPOSTA, não a da nossa coleta.

A referência é `data_proposta`, remontada de DIA_PROP+MES_PROP+ANO_PROP (as
variáveis oficiais do SIconv). Ordenar por `cache_atualizado_em` embaralhava
safras: uma proposta de 2019 recoletada hoje aparecia na frente de uma criada
este mês, só porque a coleta passou por ela depois.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion.normalizer import normalize
from src.services import propostas as service

from .conftest import _owner_engine


async def _seed(id_externo: str, ibge: str, data_proposta: str | None, dias_atras: int) -> None:
    """Proposta com data de criação própria e um instante de coleta distinto."""
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                "data_proposta, cache_atualizado_em) VALUES "
                "('transferegov_ff',:e,:t,:ibge,:dp, :cache)"
            ),
            {
                "e": id_externo,
                "t": f"Proposta {id_externo}",
                "ibge": ibge,
                "dp": date.fromisoformat(data_proposta) if data_proposta else None,
                "cache": datetime.now(UTC) - timedelta(days=dias_atras),
            },
        )


async def test_listagem_ordena_pela_data_da_proposta(seed_user, seed_municipio) -> None:
    u = await seed_user("ordem@x.com")
    await seed_municipio(u, "2611606")
    # a mais ANTIGA foi a última a passar pela coleta — pela ordem velha
    # (cache_atualizado_em) ela lideraria a lista
    await _seed("VELHA", "2611606", "2019-05-02", 0)
    await _seed("NOVA", "2611606", "2026-03-07", 10)
    await _seed("MEIO", "2611606", "2024-01-15", 5)

    async with rls_session(u) as s:
        rows = await service.listar(s)

    assert [p.id_externo for p in rows] == ["NOVA", "MEIO", "VELHA"]


async def test_proposta_sem_data_de_criacao_vai_para_o_fim(seed_user, seed_municipio) -> None:
    """Sem sinal de criação a proposta não some da lista — só não disputa a
    frente com quem tem data (nullslast); entre elas vale a coleta."""
    u = await seed_user("ordem2@x.com")
    await seed_municipio(u, "2611606")
    await _seed("SEM_DATA", "2611606", None, 0)
    await _seed("COM_DATA", "2611606", "2020-02-02", 9)

    async with rls_session(u) as s:
        rows = await service.listar(s)

    assert [p.id_externo for p in rows] == ["COM_DATA", "SEM_DATA"]


def test_normalizador_remonta_a_data_dos_tres_componentes() -> None:
    """DIA_PROP+MES_PROP+ANO_PROP vencem qualquer candidato de coluna única —
    é a data oficial de criação na fonte (o CSV do SIconv manda em CAIXA ALTA)."""
    canonica = normalize(
        RawRecord(
            source_id="transferegov_disc",
            id_externo="900123",
            raw={
                "NR_CONVENIO": "900123",
                "DIA_PROP": "7",
                "MES_PROP": "03",
                "ANO_PROP": "2026",
                # candidato de coluna única, que já marcou proposta com data errada
                "DIA_PROPOSTA": "2019-05-02",
            },
        )
    )
    assert canonica.data_proposta == date(2026, 3, 7)
