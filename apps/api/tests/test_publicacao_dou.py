"""Double-check da publicação no DOU Seção 3 (§56c).

A regra do cliente: proposta publicada SEMPRE tem nota de empenho, então a NE
naquele município, procurada no Diário Oficial, responde "saiu ou não saiu?" por
um caminho independente do campo da ficha.

Os testes cobrem as três coisas que, erradas, produziriam de volta o defeito que
originou tudo isto — a tela afirmando o que a fonte não disse:

1. **não achar ≠ não publicado** (falso negativo é o mesmo defeito ao contrário);
2. **duas âncoras** — NE isolada não prova; é preciso o município na mesma matéria;
3. **o termo é o código do INSTRUMENTO**, não o número da proposta.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from src.connectors import dou
from src.db.session import rls_session
from src.models.proposta import Proposta
from src.services import andamento, publicacao_dou
from src.services import publicacao as publicacao_service
from tests.conftest import _owner_engine

# O extrato real (DOU nº 114, 22/06/2026, Seção 3) que o gestor mandou como
# referência — com a hifenização/quebra de coluna que o jornal produz.
EXTRATO = (
    "EXTRATO DE CONTRATO Contrato de Repasse nº 999293/2026, firmado pelo "
    "MUNICÍPIO DE APUIARÉS-CE, CNPJ 07.438.468/0001-01, junto à União "
    "Federal por intermédio do MINISTÉRIO DO ESPORTE; Objeto CONSTRUÇÃO DE "
    "CAMPO DE FUTEBOL SOCIETY; NE 2026NE001244; Assinado em 18/06/2026"
)


def _pagina(itens: list[dict]) -> str:
    return (
        "<html><body>"
        f'<script id="params" type="application/json">{json.dumps({"jsonArray": itens})}</script>'
        "</body></html>"
    )


# ── leitura da busca ───────────────────────────────────────────────────────
def test_parse_le_os_resultados_embutidos() -> None:
    pagina = _pagina(
        [
            {
                "title": "EXTRATO DE CONTRATO",
                "content": f"<p class='identifica'>{EXTRATO}</p>",
                "pubDate": "22/06/2026",
                "pubName": "DO3",
                "editionNumber": "114",
                "urlTitle": "/web/dou/-/extrato-de-contrato-999293",
            }
        ]
    )
    (materia,) = dou.parse_resultados(pagina)
    assert materia.titulo == "EXTRATO DE CONTRATO"
    assert "APUIARÉS" in materia.texto
    assert materia.data and materia.data.isoformat() == "2026-06-22"
    assert materia.edicao == "114"
    assert materia.url and materia.url.startswith("https://www.in.gov.br/")


def test_pagina_sem_resultados_e_INDISPONIVEL_e_nao_vazio() -> None:
    """"Não consegui perguntar" não pode virar "não foi publicado"."""
    with pytest.raises(dou.DouIndisponivel):
        dou.parse_resultados("<html><body>Just a moment…</body></html>")


# ── casamento: duas âncoras, sempre ────────────────────────────────────────
def _materia(texto: str) -> dou.Publicacao:
    return dou.Publicacao(titulo="EXTRATO DE CONTRATO", texto=texto)


def test_casa_exige_a_ne_e_o_municipio() -> None:
    materia = _materia(EXTRATO)
    assert publicacao_dou.casa(materia, "2026NE001244", "apuiares") is True
    # a mesma NE em matéria de OUTRO município não prova esta proposta
    assert publicacao_dou.casa(materia, "2026NE001244", "fortaleza") is False
    # município certo, NE que não está na matéria: também não prova
    assert publicacao_dou.casa(materia, "2026NE999999", "apuiares") is False


def test_casa_sobrevive_a_quebra_de_coluna_do_jornal() -> None:
    """O DOU sai em coluna estreita: "MUNIC ÍPIO DE APUIAR ÉS" é o texto real."""
    materia = _materia("Contrato de Repasse 999293/2026 MUNIC ÍPIO DE APUIAR ÉS-CE NE 2026NE001244")
    assert publicacao_dou.casa(materia, "2026NE001244", "apuiares") is True


# ── o termo do instrumento ─────────────────────────────────────────────────
def test_codigo_do_instrumento_e_nao_o_numero_da_proposta() -> None:
    """Na ficha são campos diferentes (proposta 023950/2026, instrumento
    999293) e quem sai no extrato do DOU é o instrumento."""
    p = Proposta(
        numero_proposta="023950/2026",
        execucao={"webapp": {"instrumento": "999293"}},
    )
    assert publicacao_dou.codigo_instrumento(p) == "999293"
    assert publicacao_dou.codigo_instrumento(Proposta(execucao={})) is None


# ── o carimbo ──────────────────────────────────────────────────────────────
def test_confirmacao_carimba_com_a_prova_e_vence_a_ficha() -> None:
    conf = publicacao_dou.Conferencia(
        confirmado=True,
        evidencias=[
            publicacao_dou.Evidencia(
                termo="2026NE001244",
                titulo="EXTRATO DE CONTRATO",
                data="2026-06-22",
                url="https://www.in.gov.br/web/dou/-/x",
            )
        ],
    )
    marca = publicacao_dou.carimbo(conf)
    assert marca and marca["situacao_publicacao"] == "Publicado"

    leitura = publicacao_service.resolver(
        {"situacao_publicacao": "Não Publicado", "dou": marca}
    )
    assert leitura.estado == publicacao_service.PUBLICADO
    assert leitura.origem == publicacao_service.ORIGEM_DOU


def test_nao_encontrado_nao_carimba_nada() -> None:
    """Guardar "não achei" faria a leitura herdar um negativo que o DOU não deu."""
    assert publicacao_dou.carimbo(publicacao_dou.Conferencia(status="ok")) is None
    assert publicacao_dou.carimbo(publicacao_dou.Conferencia(status="erro")) is None


# ── ponta a ponta, sob RLS ─────────────────────────────────────────────────
async def _seed_empenho(numero_proposta: str, numero: str, ibge: str) -> None:
    """O elo do empenho é o NÚMERO da proposta (não FK) — como na fonte."""
    async with _owner_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.plataforma','on',true)"))
        await conn.execute(
            text(
                "INSERT INTO proposta_empenhos (id, fonte, id_externo, numero_proposta, "
                "numero_empenho, municipio_ibge, cache_atualizado_em) "
                "VALUES (:i,'siconv_webapp_empenho',:e,:np,:n,:m, now())"
            ),
            {
                "i": uuid.uuid4(),
                "e": f"{numero_proposta}:{numero}",
                "np": numero_proposta,
                "n": numero,
                "m": ibge,
            },
        )


async def test_dou_confirma_publicacao_que_a_ficha_negava(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """O caso do gestor, pelo lado certo: a ficha ainda não refletiu a
    publicação e o extrato no DOU já saiu. A tela mostra os DOIS."""

    async def busca_fake(termo, **kw):
        assert termo == "2026NE001244"  # a NE vem antes do código do instrumento
        return [
            dou.Publicacao(
                titulo="EXTRATO DE CONTRATO",
                texto=EXTRATO,
                url="https://www.in.gov.br/web/dou/-/extrato",
            )
        ]

    monkeypatch.setattr(dou, "buscar", busca_fake)

    pid = await seed_proposta(
        "transferegov_disc",
        "999293",
        "2300804",
        municipio_nome="Apuiarés",
        numero_proposta="023950/2026",
        execucao=json.dumps(
            {"situacao_publicacao": "Não Publicado", "webapp": {"instrumento": "999293"}}
        ),
    )
    await _seed_empenho("023950/2026", "2026NE001244", "2300804")
    uid = await seed_user("gestor.dou@x.com")
    await seed_municipio(uid, "2300804")

    async with rls_session(uid) as s:
        pagina = await andamento.publicacao(s, pid, conferir=True)

    assert pagina is not None
    assert pagina.conferencia.status == "ok"
    assert pagina.conferencia.confirmado is True
    assert pagina.publicacao.estado == "publicado"
    assert pagina.publicacao.prova and pagina.publicacao.prova.url
    tipos = [e.tipo for e in pagina.evidencias]
    # a divergência FICA na tela: o DOU e a ficha aparecem lado a lado
    assert tipos[0] == "dou" and "campo" in tipos


async def test_dou_fora_do_ar_nao_nega_a_publicacao(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    async def cai(termo, **kw):
        raise dou.DouIndisponivel("busca do DOU respondeu 503")

    monkeypatch.setattr(dou, "buscar", cai)

    pid = await seed_proposta(
        "transferegov_disc",
        "999294",
        "2300804",
        municipio_nome="Apuiarés",
        numero_proposta="023951/2026",
        execucao=json.dumps({"situacao_publicacao": "Publicado"}),
    )
    await _seed_empenho("023951/2026", "2026NE001245", "2300804")
    uid = await seed_user("gestor.dou2@x.com")
    await seed_municipio(uid, "2300804")

    async with rls_session(uid) as s:
        pagina = await andamento.publicacao(s, pid, conferir=True)

    assert pagina is not None
    assert pagina.conferencia.status == "erro"
    assert pagina.conferencia.confirmado is False
    # o que a ficha diz continua valendo — a falha do DOU não derruba a leitura
    assert pagina.publicacao.estado == "publicado"
