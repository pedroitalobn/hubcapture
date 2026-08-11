"""Gate de qualidade da ingestão — proposta que falhou no scraping não entra.

Cobre as três camadas do gate:
  1. connector: o fallback de scraping não fabrica mais `scrape-<ibge>`;
  2. triagem determinística (`ingestion/validador.py`), na porta do upsert;
  3. auditoria por IA (`ai/validacao.py` + `jobs/validacao.py`), fora do request.

A trava central da camada 3 tem teste próprio: IA indisponível ou resposta fora
do contrato NUNCA remove dado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.ai import validacao as validacao_ai
from src.connectors import transferegov_voluntarias as voluntarias
from src.connectors.base import RawRecord
from src.db.session import rls_session
from src.ingestion import validador
from src.ingestion.merge import merge_record
from src.jobs import validacao as validacao_job
from src.models.proposta import Proposta
from src.models.sync_run import SyncRun
from src.schemas.proposta import PropostaCanonica
from src.services import consulta_avulsa

# ── Camada 2: triagem determinística ────────────────────────────────────────


def _canonica(**campos) -> PropostaCanonica:
    base = {"fonte": "transferegov_voluntarias", "id_externo": "123456/2024"}
    return PropostaCanonica(**{**base, **campos})


def test_id_fabricado_pela_coleta_nao_entra() -> None:
    """O caso que o gestor via no painel: 'scrape-2611606' no lugar do programa."""
    for id_externo in ("scrape-2611606", "scrape", "painel-3550308-0", "SCRAPE_2611606", ""):
        p = _canonica(id_externo=id_externo, titulo="Programa de saúde")
        assert validador.motivo_rejeicao(p) == validador.MOTIVO_ID_SINTETICO, id_externo


def test_registro_sem_identidade_nao_entra() -> None:
    # nada que identifique: nem nome, nem objeto, nem número
    assert validador.motivo_rejeicao(_canonica()) == validador.MOTIVO_SEM_CONTEUDO
    # valor sozinho não é identidade — é a cara da linha de TOTAL da tabela
    assert (
        validador.motivo_rejeicao(_canonica(valor_total=Decimal("1000")))
        == validador.MOTIVO_SEM_CONTEUDO
    )
    # placeholder da fonte também não conta como conteúdo
    assert (
        validador.motivo_rejeicao(_canonica(titulo="-", objeto="N/A"))
        == validador.MOTIVO_SEM_CONTEUDO
    )


def test_pagina_de_erro_no_lugar_do_conteudo_nao_entra() -> None:
    for titulo in (
        "403 Forbidden",
        "Página não encontrada",
        "Just a moment...",
        "Attention Required! | Cloudflare",
        "Enable JavaScript and cookies to continue",
        "Erro ao carregar os dados",
        "<html><body>Erro</body></html>",
        "Serviço temporariamente indisponível",
    ):
        assert validador.motivo_rejeicao(_canonica(titulo=titulo)) == validador.MOTIVO_RUIDO, titulo


def test_proposta_real_passa_mesmo_pobre() -> None:
    """Na dúvida, aceita: esconder proposta real é pior que a linha ruim."""
    assert validador.motivo_rejeicao(_canonica(titulo="UBS")) is None
    # só o número (é o que o CSV do SIconv às vezes entrega)
    assert validador.motivo_rejeicao(_canonica(numero_proposta="14275/2026")) is None
    # CAIXA ALTA e texto truncado seguem sendo proposta
    assert validador.motivo_rejeicao(_canonica(titulo="MTUR/SECULT - ALDIR BLANC - MUNI")) is None
    # "Erro" no meio da SITUAÇÃO é situação legítima da fonte, não falha de coleta
    assert (
        validador.motivo_rejeicao(
            _canonica(titulo="Construção de creche", situacao="Erro na prestação de contas")
        )
        is None
    )


def test_triagem_separa_e_explica() -> None:
    triagem = validador.triar(
        [
            _canonica(id_externo="1", titulo="Creche"),
            _canonica(id_externo="scrape-2611606", titulo="Creche"),
            _canonica(id_externo="2"),
        ]
    )
    assert [p.id_externo for p in triagem.aceitas] == ["1"]
    assert triagem.houve_descarte
    resumo = validador.resumo_descartes(triagem.descartes)
    assert "2 registro(s) descartado(s)" in resumo
    assert validador.MOTIVO_ID_SINTETICO in resumo


# ── Camada 1: o connector não fabrica mais o stub ───────────────────────────


async def test_fallback_de_scraping_gera_um_registro_por_convenio(monkeypatch) -> None:
    """Cada linha da página vira um RawRecord com o número dela — não um pacote."""

    class _ScraperFake:
        async def is_enabled(self) -> bool:
            return True

        async def extract(self, url, schema, prompt=None) -> dict:
            return {
                "convenios": [
                    {"numero": "901231/2024", "objeto": "Reforma de UBS"},
                    {"numero": "", "objeto": "Total geral"},  # rodapé da tabela
                ]
            }

    async def _api_fora(*args, **kwargs):
        raise RuntimeError("API fora do ar")

    monkeypatch.setattr(voluntarias, "get_scraper", lambda: _ScraperFake())
    monkeypatch.setattr(voluntarias, "get_json", _api_fora)

    registros = await voluntarias.TransferegovVoluntariasConnector().collect(
        "2611606", since=date(2026, 1, 1)
    )

    assert [r.id_externo for r in registros] == ["901231/2024"]
    assert all(not r.id_externo.startswith("scrape") for r in registros)
    # e a linha coletada normaliza para uma proposta legítima
    assert validador.motivo_rejeicao(merge_record(registros[0])) is None


async def test_pagina_sem_convenio_vira_incidente_nao_proposta(monkeypatch) -> None:
    """Fonte indisponível é fonte indisponível — nunca uma proposta vazia."""

    class _ScraperFake:
        async def is_enabled(self) -> bool:
            return True

        async def extract(self, url, schema, prompt=None) -> dict:
            return {"convenios": []}  # a página abriu, mas não rendeu registro

    async def _api_fora(*args, **kwargs):
        raise RuntimeError("API fora do ar")

    monkeypatch.setattr(voluntarias, "get_scraper", lambda: _ScraperFake())
    monkeypatch.setattr(voluntarias, "get_json", _api_fora)

    with pytest.raises(RuntimeError, match="API fora do ar"):
        await voluntarias.TransferegovVoluntariasConnector().collect(
            "2611606", since=date(2026, 1, 1)
        )


# ── Camada 2 no pipeline: a triagem barra antes do upsert ───────────────────


async def test_ingestao_grava_a_boa_e_descarta_o_residuo(seed_user, seed_municipio) -> None:
    u = await seed_user("ing@x.com")
    await seed_municipio(u, "2611606")

    registros = [
        RawRecord(
            source_id="transferegov_voluntarias",
            id_externo="901231/2024",
            municipio_ibge="2611606",
            endpoint="convenio",
            raw={"plano_acao": {"objeto": "Reforma de UBS", "numero_convenio": "901231/2024"}},
        ),
        RawRecord(  # o stub que o painel mostrava como proposta
            source_id="transferegov_voluntarias",
            id_externo="scrape-2611606",
            municipio_ibge="2611606",
            endpoint="scrape",
            raw={"modalidade": "Convênio"},
        ),
    ]

    async with rls_session(u) as s:
        gravadas, descartes = await consulta_avulsa._ingerir(s, registros)
        assert gravadas == 1
        assert descartes == [("scrape-2611606", validador.MOTIVO_ID_SINTETICO)]
        ids = (await s.execute(select(Proposta.id_externo))).scalars().all()
        assert list(ids) == ["901231/2024"]


async def test_coleta_com_descarte_e_reportada_como_degradada(
    seed_user, seed_municipio, monkeypatch
) -> None:
    """O gestor precisa distinguir 'a fonte não tem nada' de 'a fonte deu lixo'."""
    u = await seed_user("deg@x.com")
    await seed_municipio(u, "2611606")

    async def _coleta_suja(fonte: str, ibge: str) -> list:
        return [
            RawRecord(
                source_id="transferegov_ff",
                id_externo="scrape-2611606",
                municipio_ibge=ibge,
                endpoint="scrape",
                raw={},
            )
        ]

    monkeypatch.setattr(consulta_avulsa, "_coletar", _coleta_suja)

    async with rls_session(u) as s:
        await consulta_avulsa.consulta_avulsa(
            s, usuario_id=u, municipio_ibge="2611606", fonte="transferegov_ff"
        )

    async with rls_session(u) as s:
        run = (await s.execute(select(SyncRun))).scalars().one()
        assert run.status == "degradado"
        assert run.registros == 0
        assert validador.MOTIVO_ID_SINTETICO in (run.erro or "")


# ── Camada 3: auditoria por IA ──────────────────────────────────────────────


def _proposta_de_scraping(seed_proposta, id_externo: str, titulo: str):
    return seed_proposta(
        "serpro", id_externo, "2611606", titulo, {"titulo": "scrape", "_fonte": "serpro"}
    )


async def test_ia_remove_o_residuo_que_passou_pela_triagem(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Coluna desalinhada: tem id e tem texto, mas o 'título' é um valor em reais."""
    u = await seed_user("ia@x.com")
    await seed_municipio(u, "2611606")
    await _proposta_de_scraping(seed_proposta, "901231/2024", "R$ 10.000,00")

    async def _reprova(proposta):
        return validacao_ai.Veredito(valido=False, motivo="título é um valor, não um objeto")

    monkeypatch.setattr(validacao_job, "analisar", _reprova)

    async with rls_session(u) as s:
        auditoria = await validacao_job.auditar_com_ia(s)
        assert auditoria.removidas == 1
        assert (await s.execute(select(Proposta.id))).scalars().all() == []


async def test_ia_aprovada_marca_cursor_e_nao_reaudita(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    u = await seed_user("ok@x.com")
    await seed_municipio(u, "2611606")
    await _proposta_de_scraping(seed_proposta, "901231/2024", "Reforma de UBS")

    chamadas = 0

    async def _aprova(proposta):
        nonlocal chamadas
        chamadas += 1
        return validacao_ai.Veredito(valido=True, motivo="objeto de convênio")

    monkeypatch.setattr(validacao_job, "analisar", _aprova)

    async with rls_session(u) as s:
        assert (await validacao_job.auditar_com_ia(s)).aprovadas == 1
        # 2ª rodada não gasta chamada: o cursor `validacao_ia` já está gravado
        assert (await validacao_job.auditar_com_ia(s)).aprovadas == 0
    assert chamadas == 1


async def test_ia_desligada_nunca_remove(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """A trava: sem credencial de LLM o veredito é None e o dado FICA."""
    u = await seed_user("off@x.com")
    await seed_municipio(u, "2611606")
    await _proposta_de_scraping(seed_proposta, "901231/2024", "Reforma de UBS")

    async def _sem_ia(proposta):
        return None

    monkeypatch.setattr(validacao_job, "analisar", _sem_ia)

    async with rls_session(u) as s:
        auditoria = await validacao_job.auditar_com_ia(s)
        assert (auditoria.removidas, auditoria.indefinidas) == (0, 1)
        assert len((await s.execute(select(Proposta.id))).scalars().all()) == 1
        # segue pendente: será reavaliada quando houver credencial
        pendente = (await s.execute(select(Proposta.validacao_ia))).scalars().one()
        assert pendente is None


async def test_ia_nao_audita_registro_de_api(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Linha de API é estruturada — não passa pelo parser e não entra no lote."""
    u = await seed_user("api@x.com")
    await seed_municipio(u, "2611606")
    await seed_proposta(
        "transferegov_ff",
        "901231/2024",
        "2611606",
        "Reforma de UBS",
        {"titulo": "api", "_fonte": "transferegov_ff"},
    )

    async def _explode(proposta):
        raise AssertionError("registro de API não deveria ser auditado")

    monkeypatch.setattr(validacao_job, "analisar", _explode)

    async with rls_session(u) as s:
        assert (await validacao_job.auditar_com_ia(s)) == validacao_job.Auditoria()


async def test_resposta_fora_do_contrato_nao_vira_remocao(monkeypatch) -> None:
    """LLM respondendo qualquer coisa = 'não sei', nunca 'apague'."""

    async def _params(*args, **kwargs):
        return {"model": "fake/modelo", "api_key": "k"}

    monkeypatch.setattr(validacao_ai.llm_providers, "params_para", _params)

    import sys
    import types

    for conteudo in ('{"valido": "talvez"}', "não sei dizer", '{"outra": 1}'):
        modulo = types.ModuleType("litellm")

        async def _acompletion(_conteudo=conteudo, **kwargs):
            return {"choices": [{"message": {"content": _conteudo}}]}

        modulo.acompletion = _acompletion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", modulo)
        assert await validacao_ai.analisar(_canonica(titulo="Creche")) is None, conteudo
