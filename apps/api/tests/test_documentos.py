"""Documentos digitalizados da proposta (ponto 10 do feedback de 28/08).

"Quando o status da publicação for publicado, disponibilizar o arquivo": o
teste cobre onde isso pode sair errado — a lista da página virando lixo de
layout, o documento trocando de identidade entre coletas, e "não consegui
consultar" sendo apresentado como "esta proposta não tem documento".
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from src.connectors.pareceres_siconv import parse_documentos
from src.ingestion.normalizer_documento import classificar, normalize_documento
from src.models.proposta import Proposta
from src.services import andamento
from src.services import documentos_proposta as service

# A página de detalhe do SIconv, no feitio do print do cliente: tabela Struts
# sem id nem classe, com cabeçalho, linhas e um rodapé que NÃO é documento.
PAGINA = """
<html><body>
<table><tr><td>Situação</td><td>Em execução</td></tr></table>
<table>
  <tr><td class="tituloSecao">Lista de Documentos Digitalizados</td></tr>
</table>
<table>
  <tr><th>Nome Arquivo</th><th>Data Upload</th><th>&nbsp;</th></tr>
  <tr>
    <td>Publica&ccedil;&atilde;o 999293.pdf</td>
    <td>22/06/2026</td>
    <td><a href="/voluntarias/DownloadArquivo.do?id=8811">Baixar</a></td>
  </tr>
  <tr>
    <td>PM_Apuiares_-_1109227-74_-_Oficio_de_Celebracao_ao_Legislativo_assinado.pdf</td>
    <td>18/06/2026</td>
    <td><a href="#" onclick="baixar('DownloadArquivo.do?id=8812')">Baixar</a></td>
  </tr>
  <tr><td colspan="3">Total de registros: 2</td></tr>
</table>
</body></html>
"""


def test_le_a_lista_de_documentos_da_pagina() -> None:
    docs = parse_documentos(PAGINA)
    assert [d["nome"] for d in docs] == [
        "Publicação 999293.pdf",
        "PM_Apuiares_-_1109227-74_-_Oficio_de_Celebracao_ao_Legislativo_assinado.pdf",
    ]
    assert docs[0]["data_upload"] == "22/06/2026"
    # link relativo vira absoluto — o gestor clica e baixa
    assert docs[0]["url"].endswith("/voluntarias/DownloadArquivo.do?id=8811")
    # âncora morta (#) não é link: o alvo real está no onclick
    assert docs[1]["url"].endswith("DownloadArquivo.do?id=8812")


def test_cabecalho_e_rodape_nao_viram_documento() -> None:
    """Linha sem data não é documento — é layout."""
    assert parse_documentos("<html><body><table><tr><td>x</td></tr></table></body></html>") == []
    docs = parse_documentos(PAGINA)
    assert all("Total de registros" not in d["nome"] for d in docs)
    assert all(d["nome"] != "Nome Arquivo" for d in docs)


def test_especie_sai_do_nome_do_arquivo() -> None:
    assert classificar("Publicação 999293.pdf") == "publicacao"
    assert classificar("PM_-_Contrato_de_Repasse_assinado.pdf") == "contrato"
    assert classificar("Oficio_de_Celebracao_ao_Legislativo.pdf") == "oficio"
    # nome que não casa nada não vira palpite
    assert classificar("arquivo1.pdf") == "outro"
    # substring solta não vale: "contrato" está dentro de "subcontratado"
    assert classificar("determinacao.pdf") == "outro"


def test_identidade_do_documento_nao_depende_da_posicao() -> None:
    """§51: id posicional faria o mesmo documento trocar de identidade a cada
    coleta — e o cache acumularia duplicatas da mesma publicação."""
    bruto = {"nome": "Publicação 999293.pdf", "data_upload": "22/06/2026"}
    a = normalize_documento(bruto, fonte="siconv_documento", id_proposta_fonte="999293")
    b = normalize_documento(bruto, fonte="siconv_documento", id_proposta_fonte="999293")
    assert a.id_externo == b.id_externo
    # a mesma publicação em OUTRA proposta é outro registro
    outra = normalize_documento(bruto, fonte="siconv_documento", id_proposta_fonte="777")
    assert outra.id_externo != a.id_externo


def test_linha_sem_nome_nao_entra() -> None:
    assert normalize_documento({"data_upload": "22/06/2026"}, fonte="f") is None


# ── ponta a ponta, sob RLS ──────────────────────────────────────────────────
async def test_documentos_da_proposta_entram_no_cache(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    from src.db.session import rls_session

    uid = await seed_user("docs@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta(
        "transferegov_disc", "999293", "3550308", numero_proposta="23950/2026"
    )

    async with rls_session(uid) as s:
        itens, coleta = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
    assert coleta.status == "ok"
    # a PUBLICAÇÃO vem primeiro: é o documento que o gestor procura
    assert itens[0].tipo == "publicacao"
    assert itens[0].url

    # segunda coleta não duplica (identidade estável)
    async with rls_session(uid) as s:
        itens2, _ = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
    assert len(itens2) == len(itens) == 2


async def test_fonte_fora_do_ar_nao_apaga_o_que_ja_esta_em_cache(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """"Não consegui consultar" ≠ "não tem documento"."""
    from src.db.session import rls_session

    class ConnectorOk:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

    class ConnectorMorto:
        async def documentos_por_id_proposta(self, id_proposta):
            raise RuntimeError("SSO do acesso livre recusou")

    uid = await seed_user("docserro@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorOk(),
    )
    async with rls_session(uid) as s:
        await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorMorto(),
    )
    async with rls_session(uid) as s:
        itens, coleta = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
    assert coleta.status == "erro"
    assert len(itens) == 2  # o que já estava continua na tela


async def test_documento_de_outro_territorio_nao_vaza(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    from src.db.session import rls_session

    dono = await seed_user("dono-doc@x.com")
    await seed_municipio(dono, "3550308")
    estranho = await seed_user("estranho-doc@x.com")
    await seed_municipio(estranho, "2611606")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")

    async with rls_session(dono) as s:
        await andamento.documentos(s, pid, atualizar=True, usuario_id=dono)
    async with rls_session(estranho) as s:
        assert await andamento.documentos(s, pid, usuario_id=estranho) is None


async def test_fonte_sem_lista_de_documentos_diz_isso(
    seed_user, seed_municipio, seed_proposta
) -> None:
    """FNS/FNDE não têm essa lista: a resposta é "fonte não suportada", que é
    diferente de "esta proposta não tem documento"."""
    from src.db.session import rls_session

    uid = await seed_user("docsfns@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("fns", "X-1", "3550308")
    async with rls_session(uid) as s:
        itens, coleta = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
    assert coleta.status == "fonte_nao_suportada"
    assert itens == []


async def _carregar(session, pid: uuid.UUID) -> Proposta:
    return (await session.execute(select(Proposta).where(Proposta.id == pid))).scalar_one()
