"""Hierarquia de exibição: o município lidera, o identificador é secundário.

Seção 23 do CLAUDE.md. A regra vale em TODA superfície de saída — header da
tela, PDF, alerta de WhatsApp, contexto do RAG e prompt da curadoria — então os
testes cobrem as funções formatadoras de cada uma. Todos puros (sem banco).
"""

from __future__ import annotations

import base64
import re
import uuid
import zlib
from decimal import Decimal

from src.ai.resumo import _contexto
from src.models.proposta import Proposta
from src.schemas.conformidade import ConformidadeRead
from src.schemas.proposta import PropostaCanonica, PropostaRead
from src.services.dispatch_alerts import _formatar
from src.services.municipios import _aplicar, rotulo, uf_do_ibge
from src.services.pdf import gerar_pdf_proposta
from src.services.rag import montar_contexto

EXECUCAO = {"valor_empenhado": "100000.00", "valor_pago": "40000.00"}


def _proposta(**kw) -> Proposta:
    base = dict(
        id=uuid.uuid4(),
        fonte="transferegov_esp",
        id_externo="PL-9",
        numero_proposta="043210/2025",
        titulo="Ampliação de UBS",
        municipio_ibge="3550308",
        municipio_nome="São Paulo",
        uf="SP",
        valor_total=Decimal("1500000.00"),
        situacao="Em análise",
        execucao=dict(EXECUCAO),
    )
    return Proposta(**{**base, **kw})


# ── Rótulo do município ─────────────────────────────────────────────────────


def test_uf_sai_do_prefixo_do_ibge() -> None:
    assert uf_do_ibge("3550308") == "SP"
    assert uf_do_ibge("2611606") == "PE"
    assert uf_do_ibge("5300108") == "DF"
    assert uf_do_ibge("9999999") is None
    assert uf_do_ibge(None) is None


def test_rotulo_poe_o_nome_na_frente() -> None:
    assert rotulo("São Paulo", "SP", "3550308") == "São Paulo/SP"
    assert rotulo("São Paulo", None, "3550308") == "São Paulo/SP"  # UF vem do IBGE


def test_rotulo_sem_nome_nunca_devolve_numero_solto() -> None:
    assert rotulo(None, None, "3550308") == "Município 3550308 (SP)"
    assert rotulo(None, None, "9999999") == "Município 9999999"
    assert rotulo(None, None, None) == "Município não informado"


# ── Enriquecimento (o nome só lidera se existir) ────────────────────────────


def _read(**kw) -> PropostaRead:
    base = {
        "id": uuid.uuid4(),
        "fonte": "transferegov_ff",
        "id_externo": "PA-1",
        "municipio_ibge": "3550308",
    }
    return PropostaRead(**{**base, **kw})


def test_enriquecer_completa_nome_pelo_territorio() -> None:
    item = _aplicar(_read(), {"3550308": ("São Paulo", "SP")})
    assert item.municipio_nome == "São Paulo"
    assert item.uf == "SP"


def test_enriquecer_nao_sobrescreve_o_que_a_fonte_trouxe() -> None:
    item = _aplicar(
        _read(municipio_nome="São Paulo (fonte)", uf="SP"),
        {"3550308": ("Outro nome", "RJ")},
    )
    assert item.municipio_nome == "São Paulo (fonte)"
    assert item.uf == "SP"


def test_enriquecer_deriva_uf_quando_o_territorio_nao_tem() -> None:
    item = _aplicar(_read(), {})
    assert item.municipio_nome is None  # não inventa nome
    assert item.uf == "SP"  # mas a UF sai do próprio código


def test_conformidade_tambem_carrega_municipio() -> None:
    r = ConformidadeRead(
        id=uuid.uuid4(), municipio_ibge="2611606", tipo="cauc", numero="1.1"
    )
    item = _aplicar(r, {"2611606": ("Recife", None)})
    assert item.municipio_nome == "Recife"
    assert item.uf == "PE"


# ── PDF ─────────────────────────────────────────────────────────────────────


def _texto(pdf: bytes) -> str:
    """Texto plano do PDF, na ordem de desenho (streams ASCII85+Flate)."""
    partes: list[bytes] = []
    for bloco in re.findall(rb"stream(.*?)endstream", pdf, re.S):
        dados = bloco.strip()
        try:
            dados = base64.a85decode(dados, adobe=True)
        except ValueError:
            pass
        try:
            dados = zlib.decompress(dados)
        except zlib.error:
            pass
        partes.append(dados)
    bruto = b" ".join(partes).decode("latin-1", errors="ignore")
    return " ".join(re.findall(r"\((.*?)\)", bruto))


def test_pdf_abre_pelo_municipio_e_nao_pelo_identificador() -> None:
    texto = _texto(gerar_pdf_proposta(_proposta()))
    assert texto.index("Paulo") < texto.index("043210")


def test_pdf_traz_o_empenho() -> None:
    texto = _texto(gerar_pdf_proposta(_proposta()))
    assert "Empenho" in texto
    assert "100.000,00" in texto  # empenhado
    assert "60.000,00" in texto  # empenhado a utilizar (100k - 40k pagos)


def test_pdf_sem_execucao_ainda_sai() -> None:
    texto = _texto(gerar_pdf_proposta(_proposta(execucao=None)))
    assert "Paulo" in texto and "Identifica" in texto


def test_pdf_sem_nome_no_cache_usa_o_nome_do_territorio() -> None:
    pdf = gerar_pdf_proposta(
        _proposta(municipio_nome=None, uf=None), municipio_nome="Recife", uf="PE"
    )
    assert "Recife/PE" in _texto(pdf)


def test_pdf_sem_nome_algum_rotula_o_codigo() -> None:
    texto = _texto(gerar_pdf_proposta(_proposta(municipio_nome=None, uf=None)))
    assert "3550308" in texto and "SP" in texto


# ── Alerta de WhatsApp · RAG · curadoria ────────────────────────────────────


class _Alerta:
    def __init__(self, proposta_id, tipo: str = "status") -> None:
        self.proposta_id = proposta_id
        self.tipo = tipo


def test_alerta_wpp_abre_pelo_municipio_e_nao_pelo_uuid() -> None:
    p = _proposta()
    msg = _formatar([_Alerta(p.id)], {p.id: p})
    assert "São Paulo/SP" in msg and "Ampliação de UBS" in msg
    assert str(p.id) not in msg  # UUID interno nunca identifica o alerta
    assert msg.index("São Paulo") < msg.index("Ampliação")


def test_alerta_sem_proposta_carregada_degrada_sem_expor_id() -> None:
    assert "Seu território" in _formatar([_Alerta(uuid.uuid4())], {})


def test_contexto_do_rag_cita_o_municipio_antes_do_id_da_fonte() -> None:
    linha = montar_contexto([_proposta()])
    assert linha.index("São Paulo/SP") < linha.index("transferegov_esp/PL-9")
    assert "empenhado: 100000.00" in linha


def test_contexto_do_rag_sem_nome_nao_devolve_codigo_solto() -> None:
    linha = montar_contexto([_proposta(municipio_nome=None, uf=None)])
    assert "Município 3550308 (SP)" in linha


def test_prompt_da_curadoria_comeca_pelo_municipio() -> None:
    canonica = PropostaCanonica(
        fonte="fns",
        id_externo="P1",
        titulo="Ampliação de UBS",
        municipio_ibge="3550308",
        municipio_nome="São Paulo",
        uf="SP",
        execucao=dict(EXECUCAO),
    )
    ctx = _contexto(canonica)
    assert ctx.startswith("Município: São Paulo/SP")
    assert "Empenhado: 100000.00" in ctx
