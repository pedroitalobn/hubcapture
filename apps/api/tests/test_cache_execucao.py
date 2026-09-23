"""§62 — a recoleta FUNDE `propostas.execucao`; não apaga o que os outros jobs gravaram.

`execucao` é um jsonb escrito por QUATRO caminhos que não se conhecem: a recoleta
(o que o connector normalizou), o pacote SIconv (`convenio`, empenhado/pago), o
enriquecimento (`webapp`, `enriquecimento`) e a conferência no DOU (`dou`). Com
`EXCLUDED.execucao` cru no ON CONFLICT, o refresh diário das 06:00 substituía o
bloco inteiro pelo que o connector tirou do CSV — e apagava a publicação lida ao
vivo, o extrato do DOU, o empenhado do pacote e o carimbo que impede o
enriquecimento de repetir a proposta. O "Publicado" da tela passava a depender da
HORA em que o gestor abria o painel.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from src.db.session import rls_session
from src.schemas.proposta import PropostaCanonica
from src.services import propostas as prop_service
from src.services import publicacao

from .conftest import _owner_engine

IBGE = "2611606"

_OUTROS_JOBS = {
    # recoleta anterior (connector)
    "valor_global": "1000.00",
    # pacote SIconv (convênio)
    "valor_empenhado": "500.00",
    "situacao_publicacao": "Publicado",
    "convenio": {"numero": "999293/2026", "situacao_publicacao": "Publicado"},
    # enriquecimento (consulta ao vivo do webapp)
    "webapp": {"situacao_publicacao": "Publicado", "empenhado": "Sim"},
    "enriquecimento": {"em": "2026-09-22T08:00:00+00:00", "viva": True},
    # conferência no DOU
    "dou": {
        "situacao_publicacao": "Publicado",
        "url": "https://in.gov.br/x",
        "nota_empenho": "2026NE001244",
    },
}


async def _execucao(id_externo: str) -> dict:
    async with _owner_engine.begin() as conn:
        return (
            await conn.execute(
                text("SELECT execucao FROM propostas WHERE id_externo = :e"), {"e": id_externo}
            )
        ).scalar_one()


async def test_recoleta_preserva_o_que_os_outros_jobs_gravaram(
    seed_user, seed_municipio, seed_proposta
) -> None:
    u = await seed_user("ex1@x.com")
    await seed_municipio(u, IBGE)
    await seed_proposta("transferegov_disc", "77", IBGE, execucao=json.dumps(_OUTROS_JOBS))
    antes = publicacao.resolver(await _execucao("77"))
    assert antes.estado == publicacao.PUBLICADO and antes.origem == publicacao.ORIGEM_DOU

    # o refresh diário recoleta do CSV: o connector só conhece valor/ano
    async with rls_session(u) as s:
        await prop_service.upsert(
            s,
            PropostaCanonica(
                fonte="transferegov_disc",
                id_externo="77",
                titulo="P (recoletada)",
                municipio_ibge=IBGE,
                execucao={"valor_global": "2000.00", "ano": "2026"},
            ),
        )

    ex = await _execucao("77")
    # o que o connector trouxe vence chave a chave…
    assert ex["valor_global"] == "2000.00"
    assert ex["ano"] == "2026"
    # …e o que ele não conhece sobrevive
    assert ex["valor_empenhado"] == "500.00"
    assert ex["webapp"] == _OUTROS_JOBS["webapp"]
    assert ex["convenio"] == _OUTROS_JOBS["convenio"]
    assert ex["dou"] == _OUTROS_JOBS["dou"]
    assert ex["enriquecimento"] == _OUTROS_JOBS["enriquecimento"]
    depois = publicacao.resolver(ex)
    assert depois.estado == publicacao.PUBLICADO and depois.origem == publicacao.ORIGEM_DOU


async def test_recoleta_sem_execucao_nao_zera_o_bloco(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """Connector que não publica execução (execucao=None) não pode apagar o jsonb."""
    u = await seed_user("ex2@x.com")
    await seed_municipio(u, IBGE)
    await seed_proposta("transferegov_disc", "78", IBGE, execucao=json.dumps(_OUTROS_JOBS))

    async with rls_session(u) as s:
        await prop_service.upsert(
            s,
            PropostaCanonica(
                fonte="transferegov_disc", id_externo="78", titulo="P", municipio_ibge=IBGE
            ),
        )

    assert await _execucao("78") == _OUTROS_JOBS


async def test_primeira_coleta_sem_execucao_continua_nula(seed_user, seed_municipio) -> None:
    """Sem linha existente e sem execução do connector, o campo segue NULL (não `{}`)."""
    u = await seed_user("ex3@x.com")
    await seed_municipio(u, IBGE)
    async with rls_session(u) as s:
        await prop_service.upsert(
            s,
            PropostaCanonica(
                fonte="transferegov_disc", id_externo="79", titulo="P", municipio_ibge=IBGE
            ),
        )
    assert await _execucao("79") is None
