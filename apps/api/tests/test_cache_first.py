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


class MockFonteCaptacao(MockConnector):
    """Connector no recorte de captação, para exercitar a busca ao vivo."""

    source_id = "transferegov_ff"


async def test_atualizar_fontes_ignora_o_cache_e_consulta_agora(seed_user, monkeypatch) -> None:
    """"Atualizar fontes" é pedido EXPLÍCITO: não pode devolver cache em silêncio.

    Sem `forcar`, o botão herdava o TTL de 6h do cache-first — o gestor clicava,
    a tela dizia "consultando as fontes…" e nenhuma fonte era consultada.
    """
    uid = await seed_user("f@f.com")
    mock = MockFonteCaptacao()
    monkeypatch.setitem(cbase._registry, mock.source_id, mock)

    async with rls_session(uid) as s:
        await service.live_search(
            s, usuario_id=uid, municipio="3106200", fonte=mock.source_id, limite=10
        )
    assert mock.calls == 1

    # leitura automática dentro do TTL: serve do cache (é o que barateia o painel)
    async with rls_session(uid) as s:
        _, _, status = await service.live_search(
            s, usuario_id=uid, municipio="3106200", fonte=mock.source_id, limite=10
        )
    assert mock.calls == 1
    assert [f["status"] for f in status] == ["cache"]  # a tela sabe que não coletou

    # pedido explícito: consulta agora, TTL ou não
    async with rls_session(uid) as s:
        _, _, status = await service.live_search(
            s,
            usuario_id=uid,
            municipio="3106200",
            fonte=mock.source_id,
            limite=10,
            forcar=True,
        )
    assert mock.calls == 2
    assert [f["status"] for f in status] == ["ok"]
    assert [f["registros"] for f in status] == [1]
