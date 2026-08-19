"""Pareceres do plano de trabalho — normalização, identidade e hash.

Testes sem banco: cobrem o que decide se o dado entra certo (de-para de campos,
identidade estável entre syncs, detecção de mudança) e o elo proposta → plano de
trabalho. A COLETA em si não é testada aqui: rota e schema de extração ainda
estão por calibrar contra a fonte viva (§36).
"""

from __future__ import annotations

from datetime import date

from src.connectors.base import RawRecord
from src.ingestion.normalizer import normalize
from src.ingestion.normalizer_parecer import normalize_parecer

# a linha como a tela de tramitação a entrega (o que o gestor vê)
LINHA = {
    "data": "01/06/2026",
    "esfera": "CONCEDENTE",
    "responsavel": "RENATA OLIVEIRA",
    "papel": "Gestor de Instrumento do Concedente",
    "cargo": "COORDENADORA-GERAL",
    "url_parecer": "https://exemplo.gov.br/parecer/1",
}


def _norm(linha: dict, **kw):
    base = dict(numero_plano_trabalho="14275/2026", fonte="transferegov_parecer")
    return normalize_parecer(linha, **{**base, **kw})


def test_le_a_linha_da_tramitacao() -> None:
    p = _norm(LINHA)
    assert p.data_parecer == date(2026, 6, 1)
    assert p.esfera == "concedente"
    assert p.responsavel == "RENATA OLIVEIRA"
    assert p.papel == "Gestor de Instrumento do Concedente"
    assert p.cargo == "COORDENADORA-GERAL"
    assert p.url_parecer == "https://exemplo.gov.br/parecer/1"
    assert p.numero_plano_trabalho == "14275/2026"


def test_le_cabecalho_em_caixa_alta() -> None:
    """A fonte manda CAIXA ALTA (§35) — o de-para tem que casar mesmo assim."""
    p = _norm({"DATA": "28/05/2026", "ESFERA": "CONCEDENTE", "RESPONSAVEL": "NATALI GOMES"})
    assert p.data_parecer == date(2026, 5, 28)
    assert p.responsavel == "NATALI GOMES"


def test_identidade_estavel_entre_syncs() -> None:
    """Mesma linha coletada de novo = mesmo id_externo, senão duplica no upsert."""
    assert _norm(LINHA).id_externo == _norm(dict(LINHA)).id_externo


def test_pareceres_diferentes_nao_colidem() -> None:
    """Duas linhas do mesmo plano em datas/pessoas diferentes são registros distintos."""
    outro = {**LINHA, "data": "28/05/2026", "responsavel": "NATALI GOMES"}
    assert _norm(LINHA).id_externo != _norm(outro).id_externo


def test_mesma_pessoa_mesmo_dia_papeis_diferentes_nao_colidem() -> None:
    # a amostra real traz linhas repetidas por papel — o papel entra na identidade
    outro = {**LINHA, "papel": "Analista Técnico do Concedente"}
    assert _norm(LINHA).id_externo != _norm(outro).id_externo


def test_hash_muda_quando_o_parecer_muda() -> None:
    igual = _norm(dict(LINHA))
    assert _norm(LINHA).hash_conteudo == igual.hash_conteudo
    mudou = _norm({**LINHA, "situacao": "Aprovado com ressalvas"})
    assert mudou.hash_conteudo != igual.hash_conteudo


def test_hash_e_proprio_do_parecer() -> None:
    """Regressão: reusar `compute_hash` da proposta daria hash igual p/ todos."""
    a = _norm(LINHA)
    b = _norm({**LINHA, "responsavel": "OUTRA PESSOA"})
    assert a.hash_conteudo != b.hash_conteudo


def test_proveniencia_marca_scraping() -> None:
    assert _norm({**LINHA, "_scraper": "playwright"}).proveniencia["responsavel"] == "scrape"
    assert _norm(LINHA).proveniencia["responsavel"] == "api"


def test_guarda_a_linha_bruta_para_calibracao() -> None:
    p = _norm({**LINHA, "COLUNA_DESCONHECIDA": "valor"})
    assert p.detalhe["COLUNA_DESCONHECIDA"] == "valor"


def test_proposta_carrega_o_numero_do_plano_de_trabalho() -> None:
    """O elo: sem ele a tela não sabe por qual número consultar o parecer."""
    p = normalize(
        RawRecord(
            source_id="transferegov_voluntarias",
            id_externo="C-1",
            municipio_ibge="3550308",
            raw={"NR_PROPOSTA": "14275/2026", "NR_PLANO_TRABALHO": "988776"},
        )
    )
    assert p.numero_plano_trabalho == "988776"
    assert p.numero_proposta == "14275/2026"


# ── Calibração contra o spec real de /planos_trabalho_analises_especiais ─────
# A rota devolve o veredito da análise, o texto e o valor reprovado, com id
# próprio — e filtra por id_plano_trabalho INTEIRO (não pelo nº da proposta).

# Payload com os nomes REAIS das colunas de /planos_trabalho_analises_especiais
# (spec oficial do módulo especiais — API nova).
API = {
    "id_plano_trabalho_analise_pt": 55123,
    "id_plano_trabalho": 988776,
    "codigo_siorg_orgao_analise_pt": 2928,
    "nome_orgao_analise_pt": "MINISTÉRIO DA SAÚDE",
    "situacao_planejamento_pt": "ENVIADO_PARA_ANALISE",
    "situacao_parecer_analise_pt": "Solicitar Complementação",
    "texto_parecer_analise_pt": "Ajustar o cronograma físico-financeiro.",
    "situacao_analise_pt": "Concluída",
    "data_analise_pt": "2026-06-01",
    "valor_reprovado_pt": 125000.50,
}


def test_le_o_payload_real_da_api() -> None:
    from decimal import Decimal

    p = _norm(API)
    assert p.data_parecer == date(2026, 6, 1)
    assert p.situacao == "Solicitar Complementação"  # o veredito
    assert p.situacao_analise == "Concluída"
    assert p.situacao_planejamento == "ENVIADO_PARA_ANALISE"
    assert p.orgao_analise == "MINISTÉRIO DA SAÚDE"
    assert p.codigo_siorg_orgao == "2928"
    assert p.valor_reprovado == Decimal("125000.50")
    assert p.texto == "Ajustar o cronograma físico-financeiro."


def test_usa_o_id_real_da_analise_como_identidade() -> None:
    assert _norm(API).id_externo == "55123"


def test_id_do_plano_vem_da_propria_linha() -> None:
    """O plano passado por parâmetro não sobrepõe o que a API devolveu."""
    assert _norm(API, numero_plano_trabalho="000").numero_plano_trabalho == "988776"


def test_valor_reprovado_entra_no_hash() -> None:
    a = _norm(API)
    b = _norm({**API, "valor_reprovado_pt": 999.0})
    assert a.hash_conteudo != b.hash_conteudo


def test_scraping_sem_id_ainda_tem_identidade_estavel() -> None:
    """A tela de tramitação não dá id — a chave sintética cobre esse caso."""
    linha = {**LINHA, "_scraper": "playwright"}
    assert _norm(linha).id_externo == _norm(dict(linha)).id_externo
    assert "|" in _norm(linha).id_externo


def test_so_id_numerico_vai_para_a_rota() -> None:
    """A rota filtra por id_plano_trabalho inteiro: '14275/2026' daria 422."""
    from src.connectors.pareceres import id_do_plano

    assert id_do_plano("988776") == "988776"
    assert id_do_plano("14275/2026") is None
    assert id_do_plano(None) is None


# ── O elo proposta → plano de trabalho (ponto 15 do feedback) ───────────────
# A rota de análises filtra pelo id INTEIRO do plano. A proposta que chega pelo
# CSV do SIconv não traz esse id, e mandar o número da proposta ("30011/2026")
# fazia o painel dizer "não consegui consultar os pareceres" numa proposta que
# TEM parecer publicado. Estes testes cobrem a resolução do id.


def test_id_do_plano_sai_do_registro_fonte() -> None:
    from src.connectors.planos_trabalho import id_no_registro_fonte

    dados = {"plano_acao": {"csv": {"ID_PLANO_TRABALHO": "988776", "NR_PROPOSTA": "30011/2026"}}}
    assert id_no_registro_fonte(dados) == "988776"


def test_registro_sem_id_do_plano_nao_inventa() -> None:
    from src.connectors.planos_trabalho import id_no_registro_fonte

    assert id_no_registro_fonte({"plano_acao": {"csv": {"NR_PROPOSTA": "30011/2026"}}}) is None
    assert id_no_registro_fonte(None) is None


def test_linha_de_outra_proposta_e_descartada() -> None:
    """Rota que ignora o filtro devolveria a tabela nacional — o refiltro barra."""
    from src.connectors.planos_trabalho import linha_e_da_proposta

    chaves = {"numero_proposta": "30011/2026"}
    assert linha_e_da_proposta({"numero_proposta": "30011/2026"}, chaves) is True
    assert linha_e_da_proposta({"numero_proposta": "99999/2026"}, chaves) is False
    # sem coluna de identificação não dá para afirmar nem negar
    assert linha_e_da_proposta({"id_plano_trabalho": 1}, chaves) is None


def test_numero_formatado_casa_com_digitos() -> None:
    from src.connectors.planos_trabalho import linha_e_da_proposta

    linha = {"numero_proposta": "300112026"}
    assert linha_e_da_proposta(linha, {"numero_proposta": "30011/2026"}) is True


def test_id_da_linha_so_aceita_inteiro() -> None:
    from src.connectors.planos_trabalho import id_da_linha

    assert id_da_linha({"id_plano_trabalho": 988776}) == "988776"
    assert id_da_linha({"numero_proposta": "30011/2026"}) is None


# ── Dialeto da rota (calibração contra o spec oficial do módulo) ───────────
# São DUAS APIs: a nova (api-publica/especiais, FastAPI) usa rota no plural,
# filtro direto e `pagina`/`tamanho_da_pagina`; a antiga (PostgREST) usa rota no
# singular, `eq.` e `limit`/`offset`. Mandar o dialeto errado no PostgREST não
# dá 404 — o filtro é ignorado e voltam as análises do país inteiro.


async def test_consulta_usa_a_rota_e_a_paginacao_da_api_nova(monkeypatch) -> None:
    from src.connectors import pareceres as mod

    capturado: dict = {}

    async def _fake_get_json(base, endpoint, params):
        capturado["endpoint"] = endpoint
        capturado["params"] = params
        return {"data": [], "total_pages": 0}

    monkeypatch.setattr(mod, "get_json", _fake_get_json)

    async def _sem_descoberta(*_a, **_kw):
        return None

    monkeypatch.setattr(mod, "descobrir", _sem_descoberta)
    await mod.ParecerConnector()._via_api("988776")

    assert capturado["endpoint"] == "planos_trabalho_analises_especiais"
    assert capturado["params"]["id_plano_trabalho"] == "988776"  # sem `eq.`
    assert capturado["params"]["pagina"] == "1"
    assert capturado["params"]["tamanho_da_pagina"] == "50"


async def test_envelope_paginado_da_api_nova_e_lido(monkeypatch) -> None:
    """A API nova responde `{data: [...]}` — ler só lista pura devolveria vazio
    e o painel diria "sem parecer" com parecer publicado na fonte."""
    from src.connectors import pareceres as mod

    async def _fake_get_json(base, endpoint, params):
        return {"data": [{"id_plano_trabalho_analise_pt": 1}], "total_pages": 1}

    monkeypatch.setattr(mod, "get_json", _fake_get_json)

    async def _sem_descoberta(*_a, **_kw):
        return None

    monkeypatch.setattr(mod, "descobrir", _sem_descoberta)
    linhas = await mod.ParecerConnector()._via_api("988776")
    assert len(linhas) == 1


async def test_dialeto_postgrest_quando_a_descoberta_aponta_a_api_antiga(monkeypatch) -> None:
    from src.connectors import pareceres as mod
    from src.connectors._especiais import Rota

    capturado: dict = {}

    async def _fake_get_json(base, endpoint, params):
        capturado["endpoint"] = endpoint
        capturado["params"] = params
        return []

    async def _descoberta_postgrest(*_a, **_kw):
        return Rota(
            endpoint="plano_trabalho_analise_especial",
            chave="id_plano_trabalho",
            postgrest=True,
        )

    monkeypatch.setattr(mod, "get_json", _fake_get_json)
    monkeypatch.setattr(mod, "descobrir", _descoberta_postgrest)
    await mod.ParecerConnector()._via_api("988776")

    assert capturado["endpoint"] == "plano_trabalho_analise_especial"
    assert capturado["params"]["id_plano_trabalho"] == "eq.988776"
    assert capturado["params"]["limit"] == "50"
    assert capturado["params"]["offset"] == "0"


def test_identidade_usa_a_coluna_real_da_analise() -> None:
    """`id_plano_trabalho_analise_pt` é o identificador no spec da API nova.
    Sem ele a identidade cairia na chave sintética — e, como a API não traz
    responsável nem papel, dois pareceres do mesmo dia colidiriam."""
    assert _norm(API).id_externo == "55123"
    outro = {**API, "id_plano_trabalho_analise_pt": 55124}
    assert _norm(outro).id_externo == "55124"


def test_valor_reprovado_le_a_coluna_real() -> None:
    p = _norm(API)
    assert p.valor_reprovado is not None and float(p.valor_reprovado) == 125000.50
