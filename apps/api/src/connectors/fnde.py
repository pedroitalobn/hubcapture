"""Connector FNDE — liberações de recursos da educação (SIMAD, consulta pública).

O FNDE não publica API REST das liberações: o que existe é a consulta pública
do SIMAD (Oracle Web Toolkit), um formulário POST cujo resultado é HTML. Ela é
ABERTA (sem login) e responde direto do IP deste servidor — não passa por
Cloudflare nem por geobloqueio, ao contrário do FNS e do TransfereGov.

O contrato, lido do formulário oficial (`internet_fnde.liberacoes_01_pc`):

  1. POST `internet_fnde.liberacoes_result_pc` com `p_uf` (sigla) +
     `p_municipio` (**IBGE de 6 dígitos**, sem o verificador — mesma pegadinha
     do FNS) + `p_ano` → LISTA DE ENTIDADES do município (CNPJ, razão social);
  2. o MESMO POST acrescido de `p_cgc=<cnpj>` → as LIBERAÇÕES daquela
     entidade: data do pagamento, nº da OB, valor, programa e conta de crédito.

Um município grande devolve centenas de entidades (cada escola tem sua unidade
executora do PDDE), e cada drill é um POST. Por isso as entidades são
ORDENADAS pelo interesse do gestor — poder público municipal primeiro — e a
rodada tem teto (`MAX_ENTIDADES`): o dinheiro que responde "quanto a prefeitura
recebeu" entra sempre; a cauda de unidades executoras entra até o limite e
completa nas coletas seguintes.

O HTML vem em **ISO-8859-1** e as datas em `19/JAN/2026` (mês abreviado em
português) — os dois pontos onde um parse ingênuo silenciosamente perde dado.
"""

from __future__ import annotations

import asyncio
import html as html_
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from ..core.config import settings
from ..services import config as config_service
from ..services import municipios as municipios_service
from . import _identidade
from .base import RawRecord, register

log = logging.getLogger(__name__)

SOURCE_ID = "fnde"

#: a consulta pública do SIMAD (o `.../sigefweb/` do default antigo é o portal,
#: não a consulta — apontava para uma rota que nunca existiu)
BASE_PADRAO = "https://www.fnde.gov.br/pls/simad/"
ENDPOINT = "internet_fnde.liberacoes_result_pc"

TIMEOUT = httpx.Timeout(60.0, connect=15.0)
#: entidades com drill por rodada (cada uma é um POST na fonte)
MAX_ENTIDADES = 25
#: pausa entre POSTs — a consulta é pública e gratuita, mas não é para martelar
PAUSA_S = 0.6
MAX_ANOS = 3

_MESES = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}

#: razão social que identifica o PODER PÚBLICO municipal — é o dinheiro que o
#: gestor administra, e por isso vai à frente da fila de drill
_RE_PODER_PUBLICO = re.compile(
    r"\b(SEC(RETARIA)?\s+MUN|PREFEITURA|MUNICIPIO|MUNIC[IÍ]PIO|FUNDO\s+MUN|"
    r"SME\b|SEDUC|EDUCA[CÇ][AÃ]O)\b",
    re.I,
)

_RE_LINHA = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_RE_CELULA = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
_RE_CNPJ = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
_RE_DATA = re.compile(r"^(\d{2})/([A-Z]{3})/(\d{4})$", re.I)


def _texto(celula: str) -> str:
    return re.sub(r"\s+", " ", html_.unescape(re.sub(r"<[^>]+>", "", celula))).strip()


def _linhas(html: str) -> list[list[str]]:
    """Toda `<tr>` do resultado como lista de células em texto limpo."""
    return [[_texto(c) for c in _RE_CELULA.findall(bloco)] for bloco in _RE_LINHA.findall(html)]


def data_iso(bruto: str) -> str | None:
    """`19/JAN/2026` → `2026-01-19`. Mês desconhecido devolve None."""
    m = _RE_DATA.match((bruto or "").strip())
    if not m:
        return None
    mes = _MESES.get(m.group(2).upper())
    if not mes:
        return None
    return f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}"


def valor_br(bruto: str) -> str | None:
    """`18.963.347,71` → `18963347.71` (texto; quem tipa é o normalizador)."""
    limpo = (bruto or "").strip().replace(".", "").replace(",", ".")
    if not limpo:
        return None
    try:
        return str(Decimal(limpo))
    except (InvalidOperation, ValueError):
        return None


def entidades_do_html(html: str) -> list[dict]:
    """As entidades do município: linhas com CNPJ + razão social + UF."""
    saida: list[dict] = []
    for cels in _linhas(html):
        if len(cels) == 3 and _RE_CNPJ.match(cels[0]):
            saida.append(
                {"cnpj": re.sub(r"\D", "", cels[0]), "cnpj_formatado": cels[0], "nome": cels[1]}
            )
    return saida


def _indice_colunas(cabecalho: list[str]) -> dict[str, int]:
    """Cabeçalho da tabela → posição de cada coluna que interessa.

    O de-para é por NOME, nunca por posição: a consulta publica DOIS layouts —
    7 colunas (Data, OB, Valor, Programa, Banco, Agência, C/C) e 8, quando o
    grupo tem parcela (PDDE Qualidade insere "Parcela" ANTES de "Programa").
    Lendo por posição, a parcela ("001") era gravada como nome do programa.
    """
    mapa: dict[str, int] = {}
    for i, celula in enumerate(cabecalho):
        c = celula.lower()
        if "data" in c:
            mapa["data"] = i
        elif c.strip() == "ob":
            mapa["ob"] = i
        elif "valor" in c:
            mapa["valor"] = i
        elif "parcela" in c:
            mapa["parcela"] = i
        elif "programa" in c:
            mapa["programa"] = i
        elif "banco" in c:
            mapa["banco"] = i
        elif "ag" in c:  # Agência (com acento na fonte)
            mapa["agencia"] = i
        elif "c/c" in c or "conta" in c:
            mapa["conta"] = i
    return mapa


def liberacoes_do_html(html: str) -> list[dict]:
    """As liberações da entidade, agrupadas por PROGRAMA como a fonte publica.

    A página é uma sequência de blocos: um subtítulo com o grupo do programa
    ("PDDE - PROGRAMA DINHEIRO DIRETO NA ESCOLA"), o cabeçalho daquele bloco e
    as linhas. Percorrer em ordem, guardando grupo e cabeçalho correntes, é o
    que permite ler os dois layouts e ainda carimbar o grupo em cada linha.

    A DATA é o que separa dado de enfeite (cabeçalho, subtítulo e a linha de
    "Total:" não abrem com data) — mais robusto que contar colunas num HTML
    gerado por Oracle Web Toolkit.
    """
    saida: list[dict] = []
    grupo: str | None = None
    colunas: dict[str, int] = {}
    for cels in _linhas(html):
        if not cels or not any(cels):
            continue
        if len(cels) == 1:
            texto = cels[0]
            # subtítulo do bloco: nem cabeçalho, nem total, nem o título da página
            if texto and "LIBERA" not in texto.upper() and "Fundo Nacional" not in texto:
                grupo = texto
            continue
        if any("data" in c.lower() for c in cels) and any(c.strip().lower() == "ob" for c in cels):
            colunas = _indice_colunas(cels)
            continue
        if not colunas or not _RE_DATA.match(cels[colunas.get("data", 0)] if cels else ""):
            continue

        def pega(nome: str) -> str | None:
            i = colunas.get(nome)
            return cels[i] if i is not None and i < len(cels) else None

        saida.append(
            {
                "data": pega("data"),
                "ob": pega("ob"),
                "valor": pega("valor"),
                "parcela": pega("parcela"),
                "programa": pega("programa"),
                "grupo": grupo,
                "banco": pega("banco"),
                "agencia": pega("agencia"),
                "conta": pega("conta"),
            }
        )
    return saida


def ordenar_entidades(entidades: list[dict]) -> list[dict]:
    """Poder público municipal primeiro; o resto em ordem estável.

    Sem isto, o teto da rodada gastaria os POSTs nas primeiras APMs em ordem
    alfabética e a Secretaria de Educação — o dado que o gestor abre o painel
    para ver — só entraria semanas depois.
    """
    return sorted(entidades, key=lambda e: (0 if _RE_PODER_PUBLICO.search(e["nome"]) else 1, e["nome"]))


class FndeConnector:
    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.fnde_base_url

    async def _base(self) -> str:
        base = await config_service.resolver("fnde_base_url") or self.base_url
        # o default antigo apontava para o portal (`/sigefweb/`), onde a
        # consulta não existe; corrige em runtime para não exigir migração
        # de config em quem já tem a chave gravada
        if "simad" not in base:
            return BASE_PADRAO
        return base

    async def _consultar(
        self, client: httpx.AsyncClient, base: str, dados: dict[str, str]
    ) -> str:
        resp = await client.post(
            base.rstrip("/") + "/" + ENDPOINT,
            data={"p_verifica": "1", "p_programa": "", "p_tp_entidade": "", "p_cgc": "", **dados},
        )
        resp.raise_for_status()
        # a fonte é ISO-8859-1 e NÃO declara charset confiável no header:
        # deixar o httpx adivinhar embaralha todo acento das razões sociais
        return resp.content.decode("latin-1", errors="replace")

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await self._base()
        uf = municipios_service.uf_do_ibge(municipio_ibge) or ""
        anos = [str(a) for a in range(since.year, date.today().year + 1)][-MAX_ANOS:]

        records: list[RawRecord] = []
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            for ano in anos:
                comum = {"p_ano": ano, "p_uf": uf, "p_municipio": municipio_ibge[:6]}
                html = await self._consultar(client, base, comum)
                entidades = ordenar_entidades(entidades_do_html(html))
                if not entidades:
                    continue
                for entidade in entidades[:MAX_ENTIDADES]:
                    await asyncio.sleep(PAUSA_S)
                    detalhe = await self._consultar(
                        client, base, {**comum, "p_cgc": entidade["cnpj"]}
                    )
                    for lib in liberacoes_do_html(detalhe):
                        linha = {**lib, **entidade, "ano": ano, "municipio_ibge": municipio_ibge}
                        raw = {
                            "data_repasse": data_iso(lib["data"]),
                            "descricao": lib["programa"],
                            "categoria": lib.get("grupo") or "FNDE",
                            "orgao_superior": "Ministério da Educação — FNDE",
                            "natureza": "repasse",
                            "valor": valor_br(lib["valor"]),
                            "competencia": ano,
                            # a OB é o documento que o gestor confere no extrato
                            "documento": lib["ob"],
                            "emenda": False,
                            "beneficiario": entidade["nome"],
                            "cnpj_beneficiario": entidade["cnpj_formatado"],
                            "detalhe": linha,
                        }
                        records.append(
                            RawRecord(
                                source_id=SOURCE_ID,
                                # OB + entidade + ano identificam a liberação; o
                                # hash do conteúdo cobre a fonte que repetir OB
                                id_externo=_identidade.id_externo(
                                    linha, municipio_ibge, prefixo="fnde"
                                ),
                                municipio_ibge=municipio_ibge,
                                endpoint=ENDPOINT,
                                raw=raw,
                            )
                        )
        return records

    async def health_check(self) -> bool:
        """Saudável = o formulário da consulta responde (não baixa resultado)."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
                resp = await client.get(
                    (await self._base()).rstrip("/") + "/internet_fnde.liberacoes_01_pc"
                )
            return resp.status_code < 400
        except Exception:  # noqa: BLE001 — health nunca levanta
            return False


register(FndeConnector())
