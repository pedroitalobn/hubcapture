"""Cache-first: consulta-avulsa só chama a fonte no miss/stale."""

from __future__ import annotations

from datetime import date

from src.connectors import base as cbase
from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.services import consulta_avulsa as service


class MockConnector:
    source_id = "mock_ff"

    def __init__(self) -> None:
        self.calls = 0

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        self.calls += 1
        return [
            RawRecord(
                source_id=self.source_id,
                id_externo="M1",
                municipio_ibge=municipio_ibge,
                raw={
                    "plano_acao": {"situacao": "Nova", "valor_total": "10"},
                    "programa": {"nome_programa": "Prog"},
                    "beneficiario": {},
                },
            )
        ]

    async def health_check(self) -> bool:
        return True


async def test_cache_first_nao_rechama_dentro_do_ttl(seed_user, monkeypatch) -> None:
    uid = await seed_user("c@c.com")
    mock = MockConnector()
    monkeypatch.setitem(cbase._registry, "mock_ff", mock)

    # 1ª consulta: cache vazio → chama a fonte e povoa
    async with rls_session(uid) as s:
        rows = await service.consulta_avulsa(
            s, usuario_id=uid, municipio_ibge="3106200", fonte="mock_ff"
        )
    assert mock.calls == 1
    assert len(rows) == 1
    assert rows[0].id_externo == "M1"

    # 2ª consulta dentro do TTL: NÃO chama a fonte de novo (serve do cache)
    async with rls_session(uid) as s:
        rows2 = await service.consulta_avulsa(
            s, usuario_id=uid, municipio_ibge="3106200", fonte="mock_ff"
        )
    assert mock.calls == 1  # continua 1 — cache hit
    assert len(rows2) == 1


async def test_consulta_avulsa_registra_municipio_avulso(seed_user, monkeypatch) -> None:
    """Sem o municipios_interesse(avulso), o RLS esconderia o próprio resultado."""
    uid = await seed_user("d@d.com")
    monkeypatch.setitem(cbase._registry, "mock_ff", MockConnector())

    async with rls_session(uid) as s:
        rows = await service.consulta_avulsa(
            s, usuario_id=uid, municipio_ibge="3106200", fonte="mock_ff"
        )
    # o resultado é visível ao próprio usuário que buscou
    assert len(rows) == 1
