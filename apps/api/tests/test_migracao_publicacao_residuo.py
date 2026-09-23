"""§62 — a migration `e6f7a8b9c0d1` limpa o rastro do refresh que apagava `execucao`.

Roda os passos da migration (importados do próprio arquivo) contra dados semeados e
confere que só o RESÍDUO sai: topo sem bloco, carimbo sem resultado, campos do
snapshot que oscilaram, alertas-artefato e repetidos. O que tem fonte fica.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from .conftest import _owner_engine

IBGE = "2611606"
_ARQUIVO = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "e6f7a8b9c0d1_publicacao_residuo_refresh.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("mig_e6f7a8b9c0d1", _ARQUIVO)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


async def _rodar_passos() -> dict[str, int]:
    mig = _migration()
    contagens: dict[str, int] = {}
    async with _owner_engine.begin() as conn:
        await conn.execute(text(mig.PLATAFORMA))
        for rotulo, sql in mig.PASSOS:
            contagens[rotulo] = (await conn.execute(text(sql))).rowcount
    return contagens


async def _execucao(id_externo: str) -> dict | None:
    async with _owner_engine.begin() as conn:
        return (
            await conn.execute(
                text("SELECT execucao FROM propostas WHERE id_externo = :e"), {"e": id_externo}
            )
        ).scalar_one()


async def test_topo_sem_bloco_sai_e_topo_com_bloco_fica(seed_user, seed_municipio, seed_proposta):
    u = await seed_user("mig1@x.com")
    await seed_municipio(u, IBGE)
    # palpite do normalizador, sozinho — é o "Publicado" indevido
    await seed_proposta(
        "serpro",
        "S1",
        IBGE,
        execucao=json.dumps({"situacao_publicacao": "Publicado", "valor_empenhado": "10"}),
    )
    # topo + bloco do pacote: fica (o bloco sustenta)
    await seed_proposta(
        "transferegov_disc",
        "D1",
        IBGE,
        execucao=json.dumps(
            {
                "situacao_publicacao": "Não Publicado",
                "convenio": {"situacao_publicacao": "Não Publicado"},
            }
        ),
    )
    # sem execução nenhuma: intocada (e sem erro)
    await seed_proposta("transferegov_disc", "D2", IBGE)

    contagens = await _rodar_passos()

    assert contagens["situacao_publicacao de topo sem bloco removida"] == 1
    s1 = await _execucao("S1")
    assert "situacao_publicacao" not in s1 and s1["valor_empenhado"] == "10"
    d1 = await _execucao("D1")
    assert d1["situacao_publicacao"] == "Não Publicado"
    assert await _execucao("D2") is None


async def test_carimbo_sem_resultado_volta_para_a_fila(seed_user, seed_municipio, seed_proposta):
    u = await seed_user("mig2@x.com")
    await seed_municipio(u, IBGE)
    await seed_proposta(
        "transferegov_disc",
        "D3",
        IBGE,
        execucao=json.dumps({"enriquecimento": {"em": "2026-09-22T08:00:00+00:00", "viva": True}}),
    )
    await seed_proposta(
        "transferegov_disc",
        "D4",
        IBGE,
        execucao=json.dumps(
            {
                "enriquecimento": {"em": "2026-09-22T08:00:00+00:00", "viva": True},
                "webapp": {"situacao_publicacao": "Publicado"},
            }
        ),
    )
    # fundo a fundo enriquece pela API, sem bloco webapp: o carimbo é legítimo
    await seed_proposta(
        "transferegov_ff",
        "F1",
        IBGE,
        execucao=json.dumps({"enriquecimento": {"em": "2026-09-22T08:00:00+00:00", "viva": True}}),
    )

    contagens = await _rodar_passos()

    assert contagens["carimbo de enriquecimento sem resultado removido"] == 1
    assert "enriquecimento" not in (await _execucao("D3"))
    assert "enriquecimento" in (await _execucao("D4"))
    assert "enriquecimento" in (await _execucao("F1"))


async def _seed_monitoramento(usuario_id, proposta_id, snapshot: dict) -> None:
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(usuario_id)}
        )
        await conn.execute(
            text(
                "INSERT INTO monitoramentos (id, usuario_id, proposta_id, ativo, snapshot) "
                "VALUES (:id, :uid, :pid, true, CAST(:snap AS jsonb))"
            ),
            {
                "id": uuid.uuid4(),
                "uid": usuario_id,
                "pid": proposta_id,
                "snap": json.dumps(snapshot),
            },
        )


async def test_snapshot_perde_so_os_campos_que_oscilaram(seed_user, seed_municipio, seed_proposta):
    u = await seed_user("mig3@x.com")
    await seed_municipio(u, IBGE)
    pid = await seed_proposta("transferegov_disc", "D5", IBGE)
    await _seed_monitoramento(
        u,
        pid,
        {
            "situacao": "Em análise",
            "prazos": [],
            "publicada": False,
            "valor_empenhado": None,
            "valor_pago": None,
            "fim_vigencia": "2027-01-01",
            "pareceres_ids": ["1"],
        },
    )

    contagens = await _rodar_passos()

    assert contagens["snapshot de monitoramento re-baseado"] == 1
    async with _owner_engine.begin() as conn:
        snap = (await conn.execute(text("SELECT snapshot FROM monitoramentos"))).scalar_one()
    assert set(snap) == {"situacao", "prazos", "fim_vigencia", "pareceres_ids"}


async def _seed_alerta(
    usuario_id, proposta_id, tipo: str, mudou: dict, created_at: str
) -> uuid.UUID:
    aid = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(usuario_id)}
        )
        await conn.execute(
            text(
                "INSERT INTO alertas "
                "(id, usuario_id, proposta_id, tipo, payload, lido, created_at) "
                "VALUES (:id, :uid, :pid, :tipo, CAST(:payload AS jsonb), false, :em)"
            ),
            {
                "id": aid,
                "uid": usuario_id,
                "pid": proposta_id,
                "tipo": tipo,
                "payload": json.dumps({"mudou": mudou, "resumo": "x"}),
                "em": datetime.fromisoformat(created_at.replace("Z", "+00:00")),
            },
        )
    return aid


async def _lido(aid: uuid.UUID) -> bool:
    async with _owner_engine.begin() as conn:
        return (
            await conn.execute(text("SELECT lido FROM alertas WHERE id = :id"), {"id": aid})
        ).scalar_one()


async def test_alertas_artefato_e_repetidos_viram_lidos(seed_user, seed_municipio, seed_proposta):
    u = await seed_user("mig4@x.com")
    await seed_municipio(u, IBGE)
    pid = await seed_proposta("transferegov_disc", "D6", IBGE)

    # artefato: publicação "desfeita" pelo apagamento
    desfez = await _seed_alerta(
        u, pid, "publicacao", {"publicada": {"antes": True, "depois": False}}, "2026-09-20T09:00Z"
    )
    # artefato: empenho que "voltou a zero"
    zerou = await _seed_alerta(
        u,
        pid,
        "empenho",
        {"valor_empenhado": {"antes": "500.00", "depois": None}},
        "2026-09-20T09:01Z",
    )
    # o MESMO fato emitido três dias seguidos: fica só o mais recente
    rep1 = await _seed_alerta(
        u, pid, "publicacao", {"publicada": {"antes": False, "depois": True}}, "2026-09-19T09:00Z"
    )
    rep2 = await _seed_alerta(
        u, pid, "publicacao", {"publicada": {"antes": False, "depois": True}}, "2026-09-20T09:00Z"
    )
    rep3 = await _seed_alerta(
        u, pid, "publicacao", {"publicada": {"antes": False, "depois": True}}, "2026-09-21T09:00Z"
    )
    # fato legítimo de outro critério: intocado
    outro = await _seed_alerta(
        u, pid, "situacao", {"situacao": {"antes": "A", "depois": "B"}}, "2026-09-21T10:00Z"
    )

    contagens = await _rodar_passos()

    assert contagens["alerta-artefato do apagamento marcado como lido"] == 2
    assert contagens["alerta repetido marcado como lido"] == 2
    assert await _lido(desfez) and await _lido(zerou)
    assert await _lido(rep1) and await _lido(rep2)
    assert not await _lido(rep3)
    assert not await _lido(outro)


async def test_migration_e_idempotente(seed_user, seed_municipio, seed_proposta):
    u = await seed_user("mig5@x.com")
    await seed_municipio(u, IBGE)
    await seed_proposta(
        "serpro", "S2", IBGE, execucao=json.dumps({"situacao_publicacao": "Publicado"})
    )
    primeira = await _rodar_passos()
    segunda = await _rodar_passos()
    assert primeira["situacao_publicacao de topo sem bloco removida"] == 1
    assert all(v == 0 for v in segunda.values())
