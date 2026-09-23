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
    """ "Não consegui consultar" ≠ "não tem documento"."""
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
    assert siconv.e_pagina_de_login("https://idp.transferegov.sistema.gov.br/idp/", None, b"<html>")
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
    """ "Não consegui baixar" é da FONTE (502 no router), nunca "não existe"."""
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
    """ "A fonte não publicou o arquivo" (404) ≠ "a fonte caiu" (502).

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


# ── §56f — trazer o máximo de documentos: parser tolerante, paginação, ponte ──


def _pagina_docs(linhas: str) -> str:
    return (
        "<html><body><table><tr><td>Situação</td><td>Em execução</td></tr></table>"
        "<table><tr><td class='tituloSecao'>Lista de Documentos Digitalizados</td></tr></table>"
        "<table><tr><th>Nome Arquivo</th><th>Data Upload</th><th>&nbsp;</th></tr>"
        f"{linhas}"
        "<tr><td colspan='3'>Total de registros</td></tr></table></body></html>"
    )


def test_href_com_entidade_html_chega_desescapado() -> None:
    """`&amp;` no atributo virava `amp;tipo` no Struts: só as linhas com mais de
    um parâmetro falhavam, e ninguém via por quê."""
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>Contrato.pdf</td><td>10/06/2026</td>"
            '<td><a href="/voluntarias/X.do?id=1&amp;tipo=2">Baixar</a></td></tr>'
        )
    )
    assert docs[0]["url"].endswith("/voluntarias/X.do?id=1&tipo=2")
    assert "&amp;" not in docs[0]["url"]


def test_onclick_fora_do_padrao_unico_ainda_da_link() -> None:
    """window.open, location.href e ação SEM query — o regex antigo exigia `.do?`."""
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>A.pdf</td><td>10/06/2026</td>"
            "<td><a href='#' onclick=\"window.open('/voluntarias/Baixar.do?id=5')\">"
            "Baixar</a></td></tr>"
            "<tr><td>B.pdf</td><td>11/06/2026</td>"
            "<td><input type='button' onclick=\"location.href='DownloadArquivo.do'\" "
            "value='Baixar'></td></tr>"
        )
    )
    assert [d["url"].rsplit("/", 1)[-1] for d in docs] == ["Baixar.do?id=5", "DownloadArquivo.do"]


def test_prefere_o_link_de_download_ao_de_detalhe() -> None:
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>A.pdf</td><td>10/06/2026</td>"
            '<td><a href="/voluntarias/DetalharArquivo.do?id=5">Detalhar</a> '
            '<a href="/voluntarias/BaixarArquivo.do?id=5">Baixar</a></td></tr>'
        )
    )
    assert docs[0]["url"].endswith("BaixarArquivo.do?id=5")


def test_id_solto_na_linha_vira_a_acao_conhecida_marcada_como_derivada() -> None:
    """Linha que só publica o id do arquivo (hidden input / função com número):
    a ação de download do webapp é montada, e a origem fica registrada."""
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>A.pdf</td><td>10/06/2026</td>"
            "<td><input type='hidden' name='idArquivo' value='8813'>"
            "<a href='#' onclick='baixar(this)'>Baixar</a></td></tr>"
            "<tr><td>B.pdf</td><td>11/06/2026</td>"
            "<td><a href='javascript:baixarArquivo(8814)'>Baixar</a></td></tr>"
        )
    )
    assert docs[0]["url"] == siconv.ACAO_BAIXAR + "8813" and docs[0]["_url_derivada"]
    assert docs[1]["url"] == siconv.ACAO_BAIXAR + "8814" and docs[1]["_url_derivada"]


def test_linha_sem_data_entra_so_quando_o_nome_e_arquivo() -> None:
    """A exigência de data descartava documento cuja data a página não mostra;
    sem a trava da extensão, o "2" do paginador viraria documento."""
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>Oficio_assinado.pdf</td>"
            '<td><a href="/voluntarias/Baixar.do?id=1">Baixar</a></td></tr>'
            '<tr><td><a href="/voluntarias/Lista.do?pagina=2">2</a></td></tr>'
        )
    )
    assert [d["nome"] for d in docs] == ["Oficio_assinado.pdf"]
    assert docs[0]["data_upload"] is None


def test_data_com_hora_e_nome_com_extensao_vencem_a_descricao() -> None:
    docs = parse_documentos(
        _pagina_docs(
            "<tr><td>Contrato de repasse assinado pelas partes em cartório</td>"
            "<td>Contrato.pdf</td><td>10/06/2026 14:32</td>"
            '<td><a href="/voluntarias/Baixar.do?id=1">Baixar</a></td></tr>'
        )
    )
    assert docs[0]["nome"] == "Contrato.pdf"
    assert docs[0]["data_upload"] == "10/06/2026"


def test_links_de_paginacao_da_lista() -> None:
    pagina = _pagina_docs(
        "<tr><td>A.pdf</td><td>10/06/2026</td>"
        '<td><a href="/voluntarias/Baixar.do?id=1">Baixar</a></td></tr>'
        '<tr><td><a href="/voluntarias/Lista.do?pagina=1">1</a> '
        '<a href="/voluntarias/Lista.do?pagina=2&amp;ordem=x">2</a> '
        "<a href='#' onclick=\"ir('/voluntarias/Lista.do?pagina=3')\">Próxima</a> "
        '<a href="/voluntarias/OutraCoisa.do">Voltar</a></td></tr>'
    )
    links = siconv.links_de_paginacao(pagina)
    assert [u.rsplit("/", 1)[-1] for u in links] == [
        "Lista.do?pagina=1",
        "Lista.do?pagina=2&ordem=x",
        "Lista.do?pagina=3",
    ]
    # fora da seção de documentos não há paginação a seguir
    assert siconv.links_de_paginacao("<html><a href='x.do?pagina=2'>2</a></html>") == []


def test_linhas_brutas_expoem_o_que_a_pagina_tem() -> None:
    linhas = siconv.linhas_brutas_documentos(
        _pagina_docs(
            "<tr><td>A.pdf</td><td>10/06/2026</td>"
            "<td><input type='hidden' name='idArquivo' value='77'>"
            "<a href='#' onclick=\"baixar('X.do?id=77')\">Baixar</a></td></tr>"
        )
    )
    assert linhas[1]["celulas"][0] == "A.pdf"
    assert linhas[1]["acoes_js"] == ["X.do?id=77"]
    assert "77" in linhas[1]["ids"]


async def test_ponte_tenta_post_quando_o_get_devolve_html() -> None:
    """Ação Struts que só lê o FORM devolve a listagem (HTML) no GET; o POST
    com os mesmos parâmetros é a segunda tentativa — antes era "login"."""

    class _Resp:
        def __init__(self, status, body, headers, url):
            self.status, self._body, self.headers, self.url = status, body, headers, url

        async def body(self):
            return self._body

    chamadas: list[tuple[str, dict]] = []

    class _Req:
        async def get(self, url, **kw):
            chamadas.append(("GET", kw))
            return _Resp(200, b"<html>listagem</html>", {"content-type": "text/html"}, url)

        async def post(self, url, **kw):
            chamadas.append(("POST", kw))
            return _Resp(
                200,
                b"%PDF-1.4 ...",
                {
                    "content-type": "application/octet-stream",
                    "content-disposition": 'attachment; filename="A.pdf"',
                },
                url,
            )

    class _Pg:
        request = _Req()

    conteudo, tipo, nome = await siconv.ParecerSiconvConnector()._requisitar_arquivo(
        _Pg(),
        "https://discricionarias.transferegov.sistema.gov.br/voluntarias/X.do?id=7&t=1",
        "ref",
    )
    assert conteudo.startswith(b"%PDF") and nome == "A.pdf"
    assert [m for m, _ in chamadas] == ["GET", "POST"]
    assert chamadas[1][1]["form"] == {"id": "7", "t": "1"}
    assert chamadas[0][1]["headers"]["Referer"] == "ref"


async def test_ponte_relata_os_dois_motivos_quando_nada_serve() -> None:
    class _Resp:
        status = 500
        headers: dict = {}
        url = "x"

        async def body(self):
            return b""

    class _Req:
        async def get(self, url, **kw):
            return _Resp()

        async def post(self, url, **kw):
            return _Resp()

    class _Pg:
        request = _Req()

    try:
        await siconv.ParecerSiconvConnector()._requisitar_arquivo(_Pg(), "https://h/x.do?id=1", "r")
    except siconv.DocumentoIndisponivel as exc:
        assert "GET: o portal do Transferegov respondeu 500" in str(exc)
        assert "POST: o portal do Transferegov respondeu 500" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("devia ter levantado DocumentoIndisponivel")
