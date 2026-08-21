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
import uuid
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
    for secao in ("VALOR TOTAL", "PRAZOS", "PEND", "DADOS GERAIS"):
        assert secao in texto, secao


def test_faixa_de_destaque_traz_o_ano_no_lugar_do_prazo() -> None:
    """A faixa do espelho mostra a SAFRA (ANO_PROP), não o prazo de vencimento —
    que vinha marcado errado e segue conferível no card 'Prazos'."""
    texto = _texto_do_pdf(
        pdf.gerar_pdf_proposta(
            _proposta(
                numero_proposta="091234/2024",
                dados_fonte={"plano_acao": {"csv": {"ANO_PROP": "2024"}}},
                prazos=[{"tipo": "envio", "data_limite": "2030-01-10"}],
            )
        )
    )
    assert "ANO DA PROPOSTA" in texto
    assert "2024" in texto
    # o rótulo do prazo saiu da faixa (trecho sem acento: o extrator é latin-1)
    assert "XIMO PRAZO" not in texto
    assert "PRAZO VENCIDO" not in texto
    assert "PRAZOS" in texto  # ...mas o card de prazos continua no documento


def test_faixa_de_destaque_traz_o_empenho_com_o_valor_global_da_fonte() -> None:
    """O espelho espelha a tela: EMPENHO carrega VL_GLOBAL_PROP, e o
    "Empenhado a utilizar" (empenhado − pago) saiu do documento — era conta
    derivada que nas propostas dava zero e não dizia nada."""
    texto = _texto_do_pdf(
        pdf.gerar_pdf_proposta(
            _proposta(
                numero_proposta="014275/2026",
                dados_fonte={"plano_acao": {"csv": {"VL_GLOBAL_PROP": "1.234.567,89"}}},
                execucao={"valor_global": "1000", "valor_empenhado": "800", "valor_pago": "300"},
            )
        )
    )
    assert "EMPENHO" in texto
    assert "1.234.567,89" in texto
    assert "A UTILIZAR" not in texto.upper()


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
    ],
)
def test_espelho_sobrevive_a_campos_gigantes(campos) -> None:
    """Nenhum registro real pode derrubar a exportação (LayoutError)."""
    conteudo = pdf.gerar_pdf_proposta(_proposta(**campos))
    assert conteudo[:5] == b"%PDF-"


# ── Complementos: andamento, empenhos e emenda ──────────────────────────────


def _evento(**campos):
    from src.schemas.andamento import EventoAndamento

    base = dict(data=date(2026, 3, 4), tipo="parecer", titulo="Aprovar", tom="ok")
    base.update(campos)
    return EventoAndamento(**base)


def _empenho(**campos):
    from src.schemas.empenho import EmpenhoRead

    base = dict(
        id=uuid.uuid4(),
        fonte="transferegov_esp",
        id_externo="E1",
        numero_empenho="2026NE000123",
        data_empenho=date(2026, 2, 10),
        valor_empenhado=Decimal("500000.00"),
        valor_pago=Decimal("120000.00"),
        ug_emitente="FUNDO NACIONAL DE SAÚDE",
    )
    base.update(campos)
    return EmpenhoRead(**base)


def _emenda(**campos):
    from src.schemas.emenda import EmendaRead

    base = dict(
        id=uuid.uuid4(),
        fonte="transferegov_esp",
        id_externo="EM1",
        numero_emenda="202612340001",
        ano=2026,
        parlamentar="FULANA DE OLIVEIRA",
        partido="XYZ",
        uf_parlamentar="RN",
        valor=Decimal("1500000.00"),
        valor_empenhado=Decimal("500000.00"),
    )
    base.update(campos)
    return EmendaRead(**base)


def test_espelho_traz_andamento_empenhos_e_emenda() -> None:
    """O espelho é o espelho da TELA: o que o detalhe mostra, o PDF leva.

    Era o defeito relatado — parecer, empenho e parlamentar autor apareciam na
    tela e sumiam no documento que o gestor encaminhava.
    """
    from src.schemas.empenho import EmpenhoResumo

    extras = pdf.Complementos(
        andamento=[
            _evento(titulo="Aprovar", ator="MARIA DA SILVA", detalhe="Concedente"),
            _evento(
                data=date(2026, 2, 10),
                tipo="empenho",
                titulo="Empenho emitido",
                valor=Decimal("500000.00"),
            ),
        ],
        empenhos=[_empenho()],
        resumo_empenhos=EmpenhoResumo(
            total=1,
            valor_empenhado=Decimal("500000.00"),
            valor_pago=Decimal("120000.00"),
        ),
        emendas=[_emenda()],
    )
    texto = _texto_do_pdf(
        pdf.gerar_pdf_proposta(_proposta(numero_proposta="014275/2026"), complementos=extras)
    )
    assert "ANDAMENTO DA PROPOSTA" in texto
    assert "Maria da Silva" in texto  # quem assinou o parecer
    assert "PARECER" in texto
    assert "EMPENHOS" in texto
    assert "2026NE000123" in texto  # o documento de empenho
    assert "EMENDA PARLAMENTAR" in texto
    assert "Fulana de Oliveira (XYZ/RN)" in texto  # o autor lidera
    assert "R$ 500.000,00" in texto


def test_espelho_sem_complementos_nao_desenha_as_secoes() -> None:
    """Sem parecer, empenho ou emenda o documento não abre seção vazia."""
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(_proposta()))
    assert "ANDAMENTO DA PROPOSTA" not in texto
    assert "EMPENHOS" not in texto
    assert "EMENDA PARLAMENTAR" not in texto


def test_empenho_anulado_sai_liquido() -> None:
    """Empenho devolvido não pode somar como recurso reservado."""
    extras = pdf.Complementos(
        empenhos=[
            _empenho(valor_empenhado=Decimal("500000.00"), valor_anulado=Decimal("500000.00"))
        ]
    )
    texto = _texto_do_pdf(pdf.gerar_pdf_proposta(_proposta(), complementos=extras))
    assert "anulado" in texto
    assert "R$ 0,00" in texto


@pytest.mark.parametrize(
    "extras",
    [
        pytest.param(
            lambda: pdf.Complementos(
                andamento=[
                    _evento(titulo=f"passo {i} " * 20, texto="TEXTO " * 2000) for i in range(60)
                ]
            ),
            id="andamento-gigante",
        ),
        pytest.param(
            lambda: pdf.Complementos(
                empenhos=[_empenho(ug_emitente="UG " * 200) for _ in range(50)]
            ),
            id="empenhos-demais",
        ),
        pytest.param(
            lambda: pdf.Complementos(
                emendas=[_emenda(parlamentar="NOME " * 300) for _ in range(30)]
            ),
            id="emendas-demais",
        ),
    ],
)
def test_complementos_gigantes_nao_derrubam_o_espelho(extras) -> None:
    """Card não se parte entre páginas: lista longa vai em cards de poucas linhas."""
    conteudo = pdf.gerar_pdf_proposta(_proposta(), complementos=extras())
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


def test_espelho_nao_carrega_plumbing_nem_origem_do_dado() -> None:
    """O documento é da PROPOSTA, não da integração que a coletou.

    Fora do espelho: proveniência campo a campo, QR/link da fonte, dump do
    registro bruto, identificador de integração e nome de fonte de dados — o
    espelho circula fora do painel e nada disso é assunto de quem recebe.
    """
    texto = _texto_do_pdf(
        pdf.gerar_pdf_proposta(
            _proposta(
                fonte="transferegov_disc",
                id_externo="30011/2026",
                numero_proposta="014275/2026",
                url_origem="https://exemplo.gov.br/proposta/1",
                proveniencia={"situacao": "scrape", "valor_total": "api"},
                dados_fonte={"plano_acao": {"csv": {"NR_PROPOSTA": "014275/2026"}}},
                execucao={"valor_global": "1000", "valor_empenhado": "800"},
            )
        )
    )
    for proibido in (
        "CONFER",  # "Conferência e proveniência"
        "PROVENI",
        "TRANSFEREGOV",
        "exemplo.gov.br",
        "30011/2026",  # identificador na fonte
        "DADOS COMPLETOS",  # anexo do registro bruto
        "NR_PROPOSTA",
        "FONTE OFICIAL",
    ):
        assert proibido not in texto.upper(), proibido
    assert "014275/2026" in texto  # ...mas a referência do gestor continua


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
