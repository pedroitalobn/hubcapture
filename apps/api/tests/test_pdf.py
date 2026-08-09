"""Espelho da proposta em PDF.

O espelho circula fora do painel (WhatsApp, e-mail do gabinete), então o que
importa aqui é: gera sempre, cabe na página e não vaza dado de outro território.
Os tetos de conteúdo têm teste próprio porque o modo de falha é traiçoeiro — um
`objeto` gigante derruba a exportação inteira com LayoutError.
"""

from __future__ import annotations

import base64
import contextlib
import re
import zlib
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.db.session import rls_session
from src.models.proposta import Proposta
from src.services import pdf
from src.services.texto import humanizar_caixa

_STRING_TJ = re.compile(rb"\(((?:\\.|[^()\\])*)\)\s*Tj", re.S)
_OCTAL = re.compile(rb"\\([0-7]{3})")


def _texto_do_pdf(conteudo: bytes) -> str:
    """Texto DESENHADO no PDF, linha a linha.

    Duas armadilhas fazem uma asserção ingênua passar (ou falhar) por acidente:
    os streams saem comprimidos (ASCII85 + Flate), e uma linha de texto costuma
    sair partida em vários operadores `Tj`. Aqui os streams são decodificados e
    os `Tj` de cada linha do stream são reunidos — é o que o leitor vê.
    """
    linhas: list[str] = []
    for bruto in re.findall(rb"stream(.*?)endstream", conteudo, re.S):
        dados = bruto.strip(b"\r\n")
        if b"~>" in dados:  # reportlab encadeia ASCII85Decode + FlateDecode
            dados = base64.a85decode(dados.split(b"~>")[0].replace(b"\n", b""))
        with contextlib.suppress(zlib.error):
            dados = zlib.decompress(dados)
        for linha in dados.splitlines():
            pedacos = _STRING_TJ.findall(linha)
            if not pedacos:
                continue
            crua = b"".join(pedacos)
            crua = _OCTAL.sub(lambda m: bytes([int(m.group(1), 8)]), crua)
            crua = re.sub(rb"\\([()\\])", rb"\1", crua)
            linhas.append(crua.decode("latin-1", "ignore"))
    return "\n".join(linhas)


async def test_gerar_pdf_proposta(seed_user, seed_municipio, seed_proposta) -> None:
    u = await seed_user("pdf@pdf.com")
    await seed_municipio(u, "3550308")
    await seed_proposta("fns", "P1", "3550308", "Ampliação de UBS")
    async with rls_session(u) as s:
        p = (await s.execute(select(Proposta))).scalars().first()
        conteudo = pdf.gerar_pdf_proposta(p)
    assert conteudo[:5] == b"%PDF-"  # é um PDF válido
    assert len(conteudo) > 500


def _proposta(**campos) -> Proposta:
    p = Proposta()
    p.fonte = campos.pop("fonte", "transferegov_ff")
    p.id_externo = campos.pop("id_externo", "X1")
    for chave, valor in campos.items():
        setattr(p, chave, valor)
    return p


def test_espelho_completo_tem_as_secoes() -> None:
    """Proposta rica → o espelho carrega marca, valor, prazo e execução."""
    p = _proposta(
        numero_proposta="091234/2024",
        titulo="AMPLIAÇÃO DA UBS CENTRAL",
        municipio_nome="MOSSORÓ",
        municipio_ibge="2408003",
        uf="RN",
        valor_total=Decimal("2487500.00"),
        situacao="EM ANÁLISE",
        prazos=[{"tipo": "envio", "data_limite": "2030-01-10"}],
        pendencias=[{"descricao": "CERTIDÃO VENCIDA", "prazo": "2030-01-05"}],
        execucao={"valor_global": "1000", "valor_empenhado": "800", "valor_pago": "300"},
        resumo_ia="Resumo gerado por IA.",
        url_origem="https://exemplo.gov.br/proposta/1",
        proveniencia={"situacao": "scrape", "valor_total": "api"},
    )
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(p))
    assert "HUB CAPTURE" in texto
    assert "ESPELHO DA PROPOSTA" in texto
    for secao in ("VALOR TOTAL", "PRAZOS", "PEND", "DADOS GERAIS", "CONFER"):
        assert secao in texto, secao


def test_espelho_de_proposta_vazia_nao_quebra() -> None:
    """Sem nenhum campo preenchido o documento ainda sai (uma página, íntegro)."""
    conteudo = pdf.gerar_pdf_proposta(_proposta(fonte="fns", id_externo="P"))
    assert conteudo[:5] == b"%PDF-"


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param({"objeto": "OBJETO " * 3000}, id="objeto-gigante"),
        pytest.param({"titulo": "T" * 5000}, id="titulo-sem-espaco"),
        pytest.param({"movimentacao": "MOV " * 4000}, id="movimentacao-gigante"),
        pytest.param(
            {
                "prazos": [
                    {"tipo": f"prazo {i} " * 20, "data_limite": "2030-01-01"} for i in range(40)
                ]
            },
            id="muitos-prazos",
        ),
        pytest.param(
            {"pendencias": [{"descricao": f"pend {i} " * 20, "prazo": None} for i in range(40)]},
            id="muitas-pendencias",
        ),
        pytest.param(
            {"dados_fonte": {f"g{g}": {f"c{i}": "v" * 900 for i in range(20)} for g in range(5)}},
            id="registro-fonte-gigante",
        ),
    ],
)
def test_espelho_sobrevive_a_campos_gigantes(campos) -> None:
    """Nenhum registro real pode derrubar a exportação (LayoutError)."""
    conteudo = pdf.gerar_pdf_proposta(_proposta(**campos))
    assert conteudo[:5] == b"%PDF-"


def test_espelho_escapa_marcacao_da_fonte() -> None:
    """Texto da fonte com `<`/`&` sai literal, não vira markup do Paragraph."""
    p = _proposta(titulo="Proposta <b>com</b> & marcação", objeto="5 < 7 & 8 > 2")
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(p))
    # as tags aparecem DESENHADAS; interpretadas, virariam negrito e sumiriam
    assert "Proposta <b>com</b> & marca" in texto
    assert "5 < 7 & 8 > 2" in texto


def test_espelho_com_execucao_zerada() -> None:
    """Barra de execução com global 0 não pode dividir por zero."""
    p = _proposta(
        execucao={"valor_global": "0", "valor_empenhado": "0", "valor_pago": "0"},
        valor_total=Decimal("0"),
        prazos=[{"tipo": "x", "data_limite": "data-invalida"}],
    )
    assert pdf.gerar_pdf_proposta(p)[:5] == b"%PDF-"


def test_data_de_emissao_e_injetavel() -> None:
    """A data impressa vem de fora — é o que torna o documento testável."""
    conteudo = pdf.gerar_pdf_proposta(_proposta(), gerado_em=datetime(2026, 3, 4, 15, 30))
    assert "04/03/2026" in _texto_do_pdf(conteudo)


def test_nome_do_arquivo_e_legivel() -> None:
    """Quem recebe o anexo precisa saber o que é sem abrir."""
    p = _proposta(numero_proposta="091234/2024", municipio_nome="MOSSORÓ")
    assert pdf.nome_arquivo(p) == "espelho-091234-2024-mossoro.pdf"  # sem acento, sem barra
    assert pdf.nome_arquivo(_proposta(id_externo="  ")).endswith(".pdf")


def test_rotulo_da_fonte_e_o_nome_do_produto() -> None:
    """O espelho mostra "TransfereGov", não o id do connector."""
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(_proposta(fonte="transferegov_disc")))
    assert "TRANSFEREGOV" in texto
    assert "TRANSFEREGOV_DISC" not in texto


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("MTUR/SECULT - ALDIR BLANC", "MTUR/SECULT - Aldir Blanc"),
        ("FUNDO_A_FUNDO", "Fundo a Fundo"),
        ("DISPONIBILIZADO", "Disponibilizado"),
        ("EM ANÁLISE", "Em Análise"),
        ("Texto já em caixa mista", "Texto já em caixa mista"),
        ("091234/2024", "091234/2024"),
        ("PREFEITURA DE SÃO PAULO", "Prefeitura de São Paulo"),
        ("", ""),
    ],
)
def test_humanizar_caixa(bruto, esperado) -> None:
    assert humanizar_caixa(bruto) == esperado


def test_humanizar_caixa_preserva_siglas() -> None:
    assert humanizar_caixa("REPASSE DO FNDE E DO FNS") == "Repasse do FNDE e do FNS"


async def test_pdf_respeita_o_territorio(seed_user, seed_municipio, seed_proposta) -> None:
    """Espelho só existe para quem enxerga a proposta.

    O endpoint monta o PDF a partir de `propostas.obter` na sessão RLS do
    request: fora do território, `obter` devolve None e a rota responde 404 —
    o documento nunca chega a ser gerado.
    """
    from src.services import propostas as propostas_service

    dono = await seed_user("dono@pdf.com")
    await seed_municipio(dono, "3550308")
    await seed_proposta("fns", "P-SP", "3550308", "UBS em São Paulo")

    outro = await seed_user("outro@pdf.com")
    await seed_municipio(outro, "2408003")

    async with rls_session(dono) as s:
        alvo = (await s.execute(select(Proposta))).scalars().first()
        proposta_id = alvo.id
        assert pdf.gerar_pdf_proposta(alvo)[:5] == b"%PDF-"

    async with rls_session(outro) as s:
        assert await propostas_service.obter(s, proposta_id) is None


def test_data_de_emissao_usa_hoje_por_padrao() -> None:
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(_proposta()))
    assert date.today().strftime("%d/%m/%Y") in texto
