"""Consulta de Programas do TransfereGov via Playwright (§64).

Três camadas: o parse PURO (HTML → registro), o fluxo de BROWSER contra uma
réplica local do formulário Struts (preenche pelos rótulos, consulta, pagina,
abre a ficha) e a gravação em `programas` convergindo com a linha do pacote.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.connectors import programas_webapp as conn
from src.core.config import settings
from src.db.session import SessionLocal
from src.jobs import siconv_diario
from src.models.programa import Programa
from src.services import programas as service

# ------------------------------------------------------------------ parse

LISTA = """
<table><tr><td>Qualificação do Proponente:</td><td><select name="q"></select></td></tr></table>
<table class="tbl">
  <tr><th>Código do Programa</th><th>Nome do Programa</th><th>Órgão Superior</th>
      <th>Data Início Recebimento de Propostas</th><th>Data Fim Recebimento de Propostas</th>
      <th>Data Fim Emenda Parlamentar</th></tr>
  <tr><td><a href="/voluntarias/programa/DetalharPrograma.do?idPrograma=77">3600020260001</a></td>
      <td>APOIO À ATENÇÃO PRIMÁRIA</td><td>MINISTERIO DA SAUDE</td>
      <td>01/09/2026</td><td>31/12/2026</td><td>15/11/2026</td></tr>
  <tr><td><a href="javascript:abrir('DetalharPrograma.do?idPrograma=78')">3600020260002</a></td>
      <td>QUADRAS ESPORTIVAS</td><td>MINISTERIO DO ESPORTE</td>
      <td></td><td>10/10/2026</td><td></td></tr>
</table>
"""

FICHA = """
<table>
 <tr><td>Código do Programa:</td><td>3600020260001</td></tr>
 <tr><td>UF Habilitada:</td><td>CE, PI e RN</td></tr>
 <tr><td>Natureza Jurídica:</td><td>Administração Pública Municipal; Consórcio Público</td></tr>
 <tr><td>Descrição:</td><td>Custeio da atenção primária</td></tr>
 <tr><td>Data Início Vigência do Programa:</td><td>01/01/2020</td></tr>
 <tr><td>Data Início para Recebimento de Propostas de Beneficiário Específico:</td>
     <td>02/09/2026</td></tr>
</table>
"""


def test_tabela_de_resultado_e_a_que_fala_de_programa():
    tab = conn.tabela_de_programas(LISTA)
    assert tab is not None and len(tab.linhas) == 2  # o formulário não é confundido


def test_linha_vira_registro_com_as_janelas_certas():
    tab = conn.tabela_de_programas(LISTA)
    p1, p2 = (conn.programa_da_linha(r) for r in tab.linhas)
    assert p1["id_programa"] == "77" and p1["codigo"] == "3600020260001"
    assert p1["nome"] == "APOIO À ATENÇÃO PRIMÁRIA"
    assert p1["orgao_superior"] == "MINISTERIO DA SAUDE"
    assert p1["inicio_proposta"] == date(2026, 9, 1)
    assert p1["fim_proposta"] == date(2026, 12, 31)
    # a porta certa: "Emenda" no rótulo vai para a janela da emenda
    assert p1["fim_emenda"] == date(2026, 11, 15)
    # link em javascript:… também rende o id do programa
    assert p2["id_programa"] == "78" and p2["fim_proposta"] == date(2026, 10, 10)


def test_ficha_completa_uf_natureza_e_ignora_vigencia():
    extra = conn.detalhe_do_programa(FICHA)
    assert extra["ufs"] == ["CE", "PI", "RN"]
    assert extra["naturezas"] == ["Administração Pública Municipal", "Consórcio Público"]
    assert extra["descricao"] == "Custeio da atenção primária"
    # vigência do PROGRAMA não é janela de inscrição
    assert "inicio_proposta" not in extra
    assert extra["inicio_beneficiario"] == date(2026, 9, 2)


def test_uf_casada_por_palavra_nao_por_substring():
    assert conn.ufs_de("Rufino") == []
    html = "<table><tr><td>Recursos suficientes:</td><td>SP</td></tr></table>"
    assert "ufs" not in conn.detalhe_do_programa(html)


# ------------------------------------------------ réplica local do webapp

FORM = """<html><head><title>Consultar Programa</title></head><body>
<form method="get" action="ConsultarPrograma.do"><input type="hidden" name="acao" value="consultar">
<table>
 <tr><td>Qualificação do Proponente:</td><td><select name="qual" onchange="">
   <option value="">Selecione</option><option value="2">Emenda Parlamentar</option>
   <option value="1">Proposta Voluntária</option></select></td></tr>
 <tr><td>Ano do Programa:</td><td><select name="ano">
   <option>2025</option><option>2026</option></select></td></tr>
 <tr><td>Apto a receber proposta:</td><td>
   <input type="radio" name="apto" value="S" id="aptoS"><label for="aptoS">Sim</label>
   <input type="radio" name="apto" value="N" id="aptoN"><label for="aptoN">Não</label></td></tr>
</table><input type="submit" value="Consultar"></form></body></html>"""


def _pagina(linhas: list[tuple[str, str, str]], proxima: str | None) -> str:
    corpo = "".join(
        f"<tr><td><a href='DetalharPrograma.do?idPrograma={i}'>{c}</a></td><td>{n}</td>"
        f"<td>MINISTERIO DA SAUDE</td><td>31/12/2026</td></tr>"
        for i, c, n in linhas
    )
    nav = f"<a href='{proxima}'>Próxima</a>" if proxima else ""
    return (
        "<html><head><title>Programas</title></head><body><table>"
        "<tr><th>Código do Programa</th><th>Nome do Programa</th><th>Órgão Superior</th>"
        f"<th>Data Fim Recebimento de Propostas</th></tr>{corpo}</table>{nav}</body></html>"
    )


class _Site(BaseHTTPRequestHandler):
    pedidos: list[dict] = []

    def log_message(self, *a):  # silêncio no pytest
        pass

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.endswith("ForwardAction.do"):
            html = "<html><head><title>Principal</title></head><body>ok</body></html>"
        elif u.path.endswith("ConsultarPrograma.do") and "acao" not in q and "pagina" not in q:
            html = FORM
        elif u.path.endswith("ConsultarPrograma.do"):
            _Site.pedidos.append(q)
            if q.get("pagina") == "2":
                html = _pagina([("79", "3600020260079", "CRECHES")], None)
            elif (q.get("qual"), q.get("ano"), q.get("apto")) == ("1", "2026", "S"):
                html = _pagina(
                    [("77", "3600020260077", "UBS"), ("78", "3600020260078", "QUADRAS")],
                    "ConsultarPrograma.do?pagina=2",
                )
            else:  # filtro não aplicado: a fonte devolve programa NÃO apto
                html = _pagina([("99", "3600020260099", "PROGRAMA FECHADO")], None)
        elif u.path.endswith("DetalharPrograma.do"):
            html = (
                "<html><body><table><tr><td>UF Habilitada:</td><td>CE</td></tr>"
                "<tr><td>Natureza Jurídica:</td><td>Administração Pública Municipal</td></tr>"
                "</table></body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()
            return
        corpo = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def site_local(monkeypatch):
    pytest.importorskip("playwright.async_api")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/voluntarias"
    monkeypatch.setattr(conn, "BASE", base)
    monkeypatch.setattr(conn, "ENTRADA", f"{base}/ForwardAction.do?Usr=guest")
    monkeypatch.setattr(conn, "CONSULTA", f"{base}/programa/ConsultarPrograma/ConsultarPrograma.do")
    _Site.pedidos = []

    async def _chromium_abre() -> str | None:
        from playwright.async_api import async_playwright

        try:
            async with async_playwright() as p:
                b = await conn._abrir_browser(p)
                await b.close()
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    motivo = asyncio.run(_chromium_abre())
    if motivo:
        srv.shutdown()
        pytest.skip(f"chromium indisponível neste ambiente: {motivo[:120]}")
    yield base
    srv.shutdown()


async def test_browser_preenche_pelos_rotulos_consulta_pagina_e_abre_ficha(site_local):
    coleta = await conn.ProgramasWebappConnector().coletar(2026)
    # os três filtros casaram pelo TEXTO e chegaram à fonte
    assert [f["ok"] for f in coleta.filtros] == [True, True, True]
    assert {"qual": "1", "ano": "2026", "apto": "S"}.items() <= _Site.pedidos[0].items()
    assert coleta.paginas == 2
    ids = sorted(p["id_programa"] for p in coleta.programas)
    assert ids == ["77", "78", "79"]  # o "fechado" do filtro errado não entrou
    ubs = next(p for p in coleta.programas if p["id_programa"] == "77")
    assert ubs["ufs"] == ["CE"] and ubs["naturezas"] == ["Administração Pública Municipal"]
    assert coleta.detalhes == 3


async def test_inventario_mostra_o_formulario_para_calibrar(site_local):
    inv = await conn.ProgramasWebappConnector().coletar(inventario=True)
    linhas = {c["linha"] for c in inv["campos"] if c.get("linha")}
    assert "Qualificação do Proponente:" in linhas
    qual = next(c for c in inv["campos"] if c["nome"] == "qual")
    assert "Proposta Voluntária" in qual["opcoes"]


# ------------------------------------------------------------ gravação


async def _owner_sql(sql: str, **params) -> list:
    owner = create_async_engine(settings.database_migrator_url, poolclass=NullPool)
    async with owner.begin() as c:
        res = await c.execute(text(sql), params)
        linhas = res.mappings().all() if res.returns_rows else []
    await owner.dispose()
    return linhas


async def test_upsert_converge_com_a_linha_do_pacote_pelo_codigo():
    await _owner_sql(
        "INSERT INTO programas (fonte, id_externo, codigo, nome, ufs, naturezas, "
        "detalhe, cache_atualizado_em) VALUES ('siconv', '500', '3600020260500', "
        "'NOME ANTIGO', '{CE}', '{\"Administração Pública Municipal\"}', "
        '\'{"descricao": "do pacote"}\', now())'
    )
    hoje = date.today()
    async with SessionLocal() as s:
        r = await service.upsert_do_webapp(
            s,
            [
                {  # sem id: casa pelo código com a linha do pacote
                    "codigo": "3600020260500",
                    "nome": "NOME NOVO",
                    "fim_proposta": hoje + timedelta(days=5),
                    "ufs": [],  # ficha não publicou: NÃO apaga a restrição do pacote
                },
                {"codigo": "3600020260600", "nome": "SÓ NA CONSULTA"},
                {"nome": "sem código nem id"},
            ],
            hoje=hoje,
        )
        await s.commit()
    assert r == {"novos": 1, "atualizados": 1, "ignorados": 1}
    linhas = await _owner_sql(
        "SELECT id_externo, nome, ufs, fim_proposta, detalhe FROM programas ORDER BY codigo"
    )
    antigo, novo = linhas
    assert antigo["id_externo"] == "500" and antigo["nome"] == "NOME NOVO"
    assert antigo["ufs"] == ["CE"] and antigo["fim_proposta"] == hoje + timedelta(days=5)
    assert antigo["detalhe"]["descricao"] == "do pacote"
    assert antigo["detalhe"]["webapp"]["apto"] is True
    assert novo["id_externo"] == "cod:3600020260600"


def test_apto_sem_data_aparece_por_poucos_dias():
    hoje = date(2026, 9, 29)
    p = Programa(
        fonte="siconv",
        id_externo="cod:1",
        situacao="Disponibilizado",
        detalhe={"webapp": {"apto": True, "verificado_em": "2026-09-28"}},
    )
    (j,) = service.janelas_ativas(p, hoje)
    assert j.status == "aberta" and j.fim is None and j.dias_restantes is None
    p.detalhe = {"webapp": {"apto": True, "verificado_em": "2026-09-20"}}
    assert service.janelas_ativas(p, hoje) == []  # consulta velha não sustenta "aberto"


def test_deduplicar_fica_com_a_linha_de_id_real():
    a = Programa(fonte="siconv", id_externo="cod:9", codigo="9")
    b = Programa(fonte="siconv", id_externo="900", codigo="9")
    assert service.deduplicar([a, b]) == [b]


def test_carga_do_pacote_funde_o_detalhe_e_limpa_o_cod():
    sql = siconv_diario.sql_upsert_programas(["id_programa"])
    assert "coalesce(programas.detalhe, '{}'::jsonb) || EXCLUDED.detalhe" in sql
    assert "LIKE 'cod:%'" in siconv_diario.SQL_LIMPA_PROGRAMAS_SEM_ID


async def test_job_pausado_nao_abre_browser(monkeypatch):
    from src.jobs import programas_webapp as job
    from src.services import fontes

    async def pausada(_f):
        return False

    monkeypatch.setattr(fontes, "esta_ativa", pausada)

    class Explode:
        async def coletar(self, *a, **k):
            raise AssertionError("não devia coletar")

    assert (await job.executar(Explode())) == {"status": "pausada"}


async def test_job_registra_degradado_quando_filtro_nao_casa(monkeypatch):
    from src.jobs import programas_webapp as job

    class Falso:
        async def coletar(self, ano):
            return conn.Coleta(
                programas=[{"codigo": "3600020260700", "nome": "X"}],
                filtros=[{"chave": "qualificacao", "ok": True}, {"chave": "apto", "ok": False}],
                paginas=1,
                detalhes=0,
            )

    r = await job.executar(Falso())
    assert r["status"] == "degradado" and r["novos"] == 1
    (run,) = await _owner_sql("SELECT status, erro FROM sync_runs WHERE fonte = 'programas_webapp'")
    assert run["status"] == "degradado" and "apto" in run["erro"]
