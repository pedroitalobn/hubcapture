"""Documentos digitalizados da proposta (ponto 10 do feedback de 28/08).

"Quando o status da publicação for publicado, disponibilizar o arquivo": o
teste cobre onde isso pode sair errado — a lista da página virando lixo de
layout, o documento trocando de identidade entre coletas, e "não consegui
consultar" sendo apresentado como "esta proposta não tem documento".
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from src.connectors import pareceres_siconv as siconv
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


def test_campo_com_data_nao_e_documento() -> None:
    """A página segue com campos como "Data da Proposta" logo depois da lista de
    documentos, e "nome + data" os fazia entrar como arquivo: a seção anunciava
    "5 arquivos na fonte" com quatro marcados "sem link na fonte" — porque não
    eram arquivos. Documento é o que se BAIXA."""
    from src.connectors.pareceres_siconv import e_documento, parse_documentos

    assert e_documento("Publicação 999293.pdf", None) is True
    assert e_documento("Declaração assinada", "https://x/baixarArquivo.do?id=9") is True
    assert e_documento("Data da Proposta", None) is False
    assert e_documento("Data Limite p/ Prestação de Contas", None) is False

    html = (
        "<b>Lista de Documentos Digitalizados</b>"
        "<table><tr><td>Nome Arquivo</td><td>Data Upload</td></tr>"
        "<tr><td>Publicacao 999293.pdf</td><td>22/06/2026</td>"
        '<tr><td><a href="baixarArquivo.do?id=9">Baixar</a></td></tr></tr></table>'
        "<table><tr><td>Data da Proposta</td><td>02/07/2026</td></tr>"
        "<tr><td>Data Inicio de Vigencia</td><td>05/07/2026</td></tr></table>"
    )
    assert [d["nome"] for d in parse_documentos(html)] == ["Publicacao 999293.pdf"]


# ── §56e: a ponte do download ───────────────────────────────────────────────
# O endereço da lista é uma ação do webapp, válida só dentro da sessão do
# acesso livre. Clicado direto pelo gestor, o Struts manda para o SSO e ele
# aterrissa em `idp.transferegov.sistema.gov.br/idp/` — tela de login onde
# devia estar o documento. Estes testes cobrem a ponte que corrige isso e as
# duas coisas que ela não pode virar: proxy aberto e entregador de HTML.
def test_so_o_portal_da_fonte_atravessa_a_ponte() -> None:
    """A URL vem de HTML raspado — é ENTRADA externa, não configuração."""
    assert siconv.e_url_da_fonte(
        "https://discricionarias.transferegov.sistema.gov.br/voluntarias/"
        "EditarDadosProposta/DetalharPropostaBaixar.do?id=7"
    )
    assert not siconv.e_url_da_fonte("https://exemplo.com/arquivo.pdf")
    assert not siconv.e_url_da_fonte("http://169.254.169.254/latest/meta-data/")
    assert not siconv.e_url_da_fonte("file:///etc/passwd")
    # host que só TERMINA parecido não é a fonte
    assert not siconv.e_url_da_fonte("https://transferegov.sistema.gov.br.mau.com/x")
    assert not siconv.e_url_da_fonte(None)


def test_tela_de_login_nunca_sai_como_documento() -> None:
    """O Struts responde 200 com o SSO quando a sessão caiu. Entregar isso com
    o nome do arquivo faria o gestor anexar um HTML de login ao processo."""
    url = "https://discricionarias.transferegov.sistema.gov.br/voluntarias/x.do"
    assert siconv.e_pagina_de_login(
        "https://idp.transferegov.sistema.gov.br/idp/", None, b"<html>"
    )
    assert siconv.e_pagina_de_login(url, "text/html; charset=ISO-8859-1", b"%PDF-1.4")
    assert siconv.e_pagina_de_login(url, None, b"\n  <!DOCTYPE html><html>")
    assert not siconv.e_pagina_de_login(url, "application/pdf", b"%PDF-1.4 ...")
    # o Struts manda octet-stream em tudo: isso é arquivo, não login
    assert not siconv.e_pagina_de_login(url, "application/octet-stream", b"%PDF-1.4")


def test_nome_e_tipo_do_arquivo() -> None:
    # a extensão do NOME vence o octet-stream genérico do portal — senão o
    # celular do gestor guarda o arquivo em vez de abrir o PDF
    assert service.content_type_de("Publicacao 999293.pdf", "application/octet-stream") == (
        "application/pdf"
    )
    assert service.content_type_de("planilha.xlsx", None).endswith("spreadsheetml.sheet")
    assert service.content_type_de("sem-extensao", "image/png") == "image/png"
    assert service.content_type_de("sem-extensao", None) == "application/octet-stream"
    # nome raspado não injeta parâmetro no Content-Disposition
    assert '"' not in service._sanear('Ofi"cio\n de Celebracao.pdf')
    assert service._sanear("   ") == "documento"
    assert siconv.nome_do_cabecalho('attachment; filename="Publicacao 999293.pdf"') == (
        "Publicacao 999293.pdf"
    )
    assert siconv.nome_do_cabecalho(None) is None


def test_cabecalho_de_download_preserva_o_acento() -> None:
    """Cabeçalho HTTP é latin-1: o nome acentuado da fonte precisa das DUAS
    formas da RFC 6266, senão sai mutilado (ou quebra a resposta)."""
    disp = service.content_disposition("Ofício de Celebração.pdf")
    assert disp.startswith('attachment; filename="Oficio de Celebracao.pdf"')
    assert "filename*=UTF-8''Of%C3%ADcio%20de%20Celebra%C3%A7%C3%A3o.pdf" in disp
    disp.encode("latin-1")  # é isso que o servidor faz ao enviar
    assert service.content_disposition("x.pdf", inline=True).startswith("inline;")


async def test_ponte_baixa_o_arquivo_da_proposta(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Ponta a ponta sob RLS: a URL sai do CACHE da proposta, nunca do cliente."""
    from src.db.session import rls_session

    pedidos: list[tuple[str, str]] = []

    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

        async def baixar_documento(self, id_proposta, url):
            pedidos.append((id_proposta, url))
            return b"%PDF-1.4 conteudo", "application/octet-stream", None

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    uid = await seed_user("ponte-doc@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")

    async with rls_session(uid) as s:
        itens, _ = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
        doc = itens[0]
        # fase 1 sob a sessão RLS; fase 2 (a coleta) já fora dela (§38)
        ref = await andamento.referencia_do_documento(s, pid, doc.id)
    assert ref is not None
    arquivo = await service.buscar(ref)

    assert arquivo is not None
    assert arquivo.conteudo.startswith(b"%PDF")
    # o tipo sai da extensão do nome, não do octet-stream do portal
    assert arquivo.content_type == "application/pdf"
    assert arquivo.nome == doc.nome
    assert pedidos == [("999293", doc.url)]


async def test_documento_de_outra_proposta_nao_baixa(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """Id de documento avulso não vira download: a busca é sempre entre os
    documentos DESTA proposta, sob RLS."""
    from src.db.session import rls_session

    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

        async def baixar_documento(self, id_proposta, url):  # pragma: no cover
            raise AssertionError("não deveria ir à fonte")

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    uid = await seed_user("ponte-outro@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")
    outra = await seed_proposta("transferegov_disc", "888111", "3550308")

    async with rls_session(uid) as s:
        itens, _ = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
        assert await andamento.referencia_do_documento(s, outra, itens[0].id) is None
        assert await andamento.referencia_do_documento(s, pid, uuid.uuid4()) is None


async def test_falha_da_fonte_sobe_como_indisponivel(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """"Não consegui baixar" é da FONTE (502 no router), nunca "não existe"."""
    import pytest

    from src.db.session import rls_session

    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            return parse_documentos(PAGINA)

        async def baixar_documento(self, id_proposta, url):
            raise siconv.DocumentoIndisponivel("o portal devolveu a tela de login")

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    uid = await seed_user("ponte-falha@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")

    async with rls_session(uid) as s:
        itens, _ = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
        ref = await andamento.referencia_do_documento(s, pid, itens[0].id)
    with pytest.raises(siconv.DocumentoIndisponivel):
        await service.buscar(ref)


async def test_documento_sem_endereco_nao_e_falha_da_fonte(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    """"A fonte não publicou o arquivo" (404) ≠ "a fonte caiu" (502).

    O gestor precisa da diferença: no primeiro caso ele pede o arquivo ao órgão
    pelo nome exato; no segundo, tenta de novo mais tarde.
    """
    import pytest

    from src.db.session import rls_session

    class ConnectorFake:
        async def documentos_por_id_proposta(self, id_proposta):
            # linha com nome de arquivo e data, mas sem link de download
            return [{"nome": "Contrato de Repasse assinado.pdf", "data_upload": "18/06/2026"}]

    monkeypatch.setattr(
        "src.services.documentos_proposta.pareceres_siconv.get_connector",
        lambda: ConnectorFake(),
    )
    uid = await seed_user("ponte-sem-url@x.com")
    await seed_municipio(uid, "3550308")
    pid = await seed_proposta("transferegov_disc", "999293", "3550308")

    async with rls_session(uid) as s:
        itens, _ = await andamento.documentos(s, pid, atualizar=True, usuario_id=uid)
        assert itens and not itens[0].url
        with pytest.raises(service.SemArquivoNaFonte):
            await andamento.referencia_do_documento(s, pid, itens[0].id)
