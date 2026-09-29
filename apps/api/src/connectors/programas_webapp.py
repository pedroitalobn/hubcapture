"""Consulta de Programas do TransfereGov — webapp SIconv, acesso livre (§64).

A página oficial que o gestor usa para achar onde se inscrever:
`/voluntarias/programa/ConsultarPrograma/ConsultarPrograma.do`, com os filtros
**Qualificação do proponente = Proposta Voluntária**, **Ano** e **Apto a
receber proposta = Sim**. O pacote de dados abertos (`programa.csv`, §63) traz
os mesmos programas, mas é atualizado com atraso; esta consulta responde no
MESMO dia em que o concedente abre a janela.

POR QUE BROWSER: é o mesmo webapp Struts dos pareceres (`pareceres_siconv`) —
a sessão anônima só nasce pelo rito do SSO com `Usr=guest`, que depende de JS.
O rito de entrada é o já validado em produção naquele connector.

NADA AQUI DEPENDE DE ID OU CLASSE CSS da página. O formulário é preenchido
achando cada campo pelo TEXTO do rótulo (e a opção pelo texto da opção), e a
tabela de resultado é lida pelo TEXTO do cabeçalho. É o que permite escrever o
connector sem poder abrir a página daqui (o sandbox de CI/agente não alcança
o gov.br) e o que o mantém de pé quando a fonte renomeia um `id`. Quando algo
não casar, `probe_programas` mostra os rótulos, as opções e os cabeçalhos que a
página REALMENTE tem — é de lá que sai a calibração (overrides no painel).

As funções de parse são PURAS (recebem HTML, devolvem dicts): o teste roda sem
rede e sem browser.
"""

from __future__ import annotations

import html as html_
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

log = logging.getLogger(__name__)

SOURCE_ID = "programas_webapp"

BASE = "https://discricionarias.transferegov.sistema.gov.br/voluntarias"
#: Entrada guest — a MESMA de `pareceres_siconv.ENTRADA`, validada em produção.
ENTRADA = (
    f"{BASE}/ForwardAction.do?modulo=Principal"
    "&path=/MostraPrincipalConsultarProposta.do&Usr=guest&Pwd=guest"
)
CONSULTA = f"{BASE}/programa/ConsultarPrograma/ConsultarPrograma.do"

TIMEOUT_MS = 60_000
MAX_PAGINAS = 40
MAX_DETALHES = 400

# ---------------------------------------------------------------- texto


def norm(texto: str | None) -> str:
    """Minúsculo, sem acento, espaço colapsado — a forma em que tudo é casado."""
    sem = unicodedata.normalize("NFD", texto or "")
    sem = "".join(c for c in sem if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem).strip().lower()


_TAGS = re.compile(r"<[^>]+>")
_LINHA = re.compile(r"<tr\b.*?</tr>", re.I | re.S)
_CELULA = re.compile(r"<t([dh])\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_TABELA = re.compile(r"<table\b.*?</table>", re.I | re.S)
_HREF = re.compile(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I)
_ACAO_JS = re.compile(r"""['"]([^'"]*\.do\?[^'"]+)['"]""", re.I)
_ID_PROGRAMA = re.compile(r"(?:idPrograma|idprograma|id)=(\d+)")
_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
_UF = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
)


def texto_celula(bruto: str) -> str:
    return re.sub(r"\s+", " ", html_.unescape(_TAGS.sub(" ", bruto))).strip()


def data_br(texto: str | None) -> date | None:
    m = _DATA.search(texto or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def ufs_de(texto: str | None) -> list[str]:
    return sorted(set(_UF.findall((texto or "").upper())))


def _url_da_linha(linha: str) -> str | None:
    for padrao in (_HREF, _ACAO_JS):
        for alvo in padrao.findall(linha):
            alvo = html_.unescape(alvo)
            if ".do" in alvo and not alvo.lower().startswith("javascript:void"):
                return urljoin(BASE + "/", alvo)
    return None


# ------------------------------------------------------ tabela de resultado


@dataclass
class Tabela:
    cabecalho: list[str]
    linhas: list[dict[str, Any]] = field(default_factory=list)


def tabelas(html_pagina: str) -> list[Tabela]:
    """Toda tabela da página com cabeçalho reconhecível, na ordem em que aparece.

    Tabelas ANINHADAS (layout Struts clássico) são lidas pela mais interna:
    o regex não guloso fecha no primeiro `</table>`, que é o da interna.
    """
    saida: list[Tabela] = []
    for bloco in _TABELA.findall(html_pagina):
        linhas = _LINHA.findall(bloco)
        if len(linhas) < 2:
            continue
        cab = [texto_celula(c) for _, c in _CELULA.findall(linhas[0])]
        if not any(cab):
            continue
        tab = Tabela(cabecalho=cab)
        for linha in linhas[1:]:
            celulas = [texto_celula(c) for _, c in _CELULA.findall(linha)]
            if not any(celulas) or len(celulas) < max(2, len(cab) // 2):
                continue
            registro: dict[str, Any] = dict(zip(cab, celulas, strict=False))
            registro["_url"] = _url_da_linha(linha)
            tab.linhas.append(registro)
        saida.append(tab)
    return saida


def tabela_de_programas(html_pagina: str) -> Tabela | None:
    """A tabela cujo cabeçalho fala de PROGRAMA — a de resultados.

    Exige "programa" OU "codigo" no cabeçalho E ao menos uma linha: o
    formulário de filtros também é uma tabela e não pode ser confundido com o
    resultado (o parse leria "Ano" e "Situação" como programas).
    """
    melhor: Tabela | None = None
    for tab in tabelas(html_pagina):
        cab = [norm(c) for c in tab.cabecalho]
        if not tab.linhas:
            continue
        if not any("programa" in c or "codigo" in c for c in cab):
            continue
        if melhor is None or len(tab.linhas) > len(melhor.linhas):
            melhor = tab
    return melhor


def _campo(registro: dict[str, Any], *termos: str, sem: tuple[str, ...] = ()) -> str | None:
    """Valor da primeira coluna cujo cabeçalho contém TODOS os termos."""
    for chave, valor in registro.items():
        if chave.startswith("_"):
            continue
        c = norm(chave)
        if all(t in c for t in termos) and not any(s in c for s in sem):
            v = (valor or "").strip()
            if v:
                return v
    return None


def _janelas(pares: dict[str, str]) -> dict[str, date | None]:
    """As três janelas do SIconv a partir de rótulos livres.

    O rótulo diz de QUAL porta é a data: "emenda" → emenda parlamentar,
    "benef" → beneficiário específico, o resto → proposta voluntária. E diz se
    é início ou fim. Casar por posição trocaria as janelas entre si.
    """
    saida: dict[str, date | None] = {}
    for rotulo, valor in pares.items():
        r = norm(rotulo)
        if not ("inicio" in r or "fim" in r or "termino" in r or "final" in r):
            continue
        if not (
            "receb" in r or "proposta" in r or "emenda" in r or "benef" in r or "vigencia" in r
        ):
            continue
        if "vigencia" in r:  # vigência do programa não é janela de inscrição
            continue
        porta = "emenda" if "emenda" in r else "beneficiario" if "benef" in r else "proposta"
        lado = "inicio" if "inicio" in r else "fim"
        d = data_br(valor)
        if d:
            saida.setdefault(f"{lado}_{porta}", d)
    return saida


def programa_da_linha(registro: dict[str, Any]) -> dict[str, Any] | None:
    """Uma linha da tabela de resultado → registro canônico de `programas`."""
    codigo = _campo(registro, "codigo")
    nome = _campo(registro, "nome") or _campo(registro, "programa", sem=("codigo", "orgao"))
    if not (codigo or nome):
        return None
    url = registro.get("_url")
    m = _ID_PROGRAMA.search(url or "")
    pares = {k: v for k, v in registro.items() if not k.startswith("_") and isinstance(v, str)}
    return {
        "id_programa": m.group(1) if m else None,
        "codigo": re.sub(r"\D", "", codigo) or codigo if codigo else None,
        "nome": nome,
        "orgao_superior": _campo(registro, "orgao", "superior") or _campo(registro, "orgao"),
        "orgao": _campo(registro, "orgao", sem=("superior",)),
        "situacao": _campo(registro, "situacao"),
        "ano": int(a) if (a := _campo(registro, "ano")) and a.isdigit() else None,
        "modalidades": [x] if (x := _campo(registro, "modalidade")) else [],
        "naturezas": [x] if (x := _campo(registro, "natureza")) else [],
        "ufs": ufs_de(_campo(registro, "uf")),
        **_janelas(pares),
        "url_detalhe": url,
    }


# ------------------------------------------------------------ detalhe


def pares_rotulados(html_pagina: str) -> dict[str, str]:
    """Pares "Rótulo: valor" da ficha (cada rótulo casa a célula seguinte).

    A ficha Struts é uma grade de `<td class=label>Rótulo</td><td>valor</td>`;
    sem depender da classe, o rótulo é a célula que termina em ":" ou que vem
    antes de uma célula de valor na mesma linha.
    """
    pares: dict[str, str] = {}
    for linha in _LINHA.findall(html_pagina):
        celulas = [texto_celula(c) for _, c in _CELULA.findall(linha)]
        for i in range(0, len(celulas) - 1):
            rotulo, valor = celulas[i], celulas[i + 1]
            if not rotulo or len(rotulo) > 120:
                continue
            if rotulo.endswith(":") or (i % 2 == 0 and valor):
                pares.setdefault(rotulo.rstrip(":").strip(), valor)
    return pares


def detalhe_do_programa(html_pagina: str) -> dict[str, Any]:
    """A ficha de UM programa → os campos que a lista não traz."""
    pares = pares_rotulados(html_pagina)

    def valor(*termos: str, sem: tuple[str, ...] = ()) -> str | None:
        for rotulo, v in pares.items():
            r = norm(rotulo)
            if all(t in r for t in termos) and not any(s in r for s in sem) and v:
                return v
        return None

    naturezas = [
        n.strip()
        for n in re.split(r"[;\n]|\s{2,}|,(?=\s*[A-Z])", valor("natureza") or "")
        if n.strip()
    ]
    modalidade = valor("modalidade")
    campos = {
        "descricao": valor("descricao", sem=("orgao",)) or valor("objetivo"),
        "acao_orcamentaria": valor("acao", "orcament"),
        "orgao_superior": valor("orgao", "superior"),
        # "uf" por PALAVRA: como substring casaria "sUFiciente", "rUFino"…
        "ufs": ufs_de(
            next((v for r, v in pares.items() if re.search(r"\bufs?\b", norm(r))), None)
            or valor("estado")
        ),
        "naturezas": naturezas,
        "modalidades": [modalidade] if modalidade else [],
        **_janelas(pares),
    }
    return {k: v for k, v in campos.items() if v not in (None, [], "")}


# ------------------------------------------------- formulário (no browser)


#: Os filtros da consulta, pelo TEXTO: (rótulo do campo, texto da opção).
#: `{ano}` é trocado pelo ano pedido. Ordem importa: a qualificação pode
#: recarregar o formulário (onchange) e apagar o que foi marcado antes.
def filtros_padrao(ano: int) -> list[dict[str, Any]]:
    return [
        {"chave": "qualificacao", "rotulos": ["qualificacao"], "opcao": ["proposta voluntaria"]},
        {"chave": "ano", "rotulos": ["ano"], "opcao": [str(ano)], "texto": str(ano)},
        {"chave": "apto", "rotulos": ["apto", "receber proposta"], "opcao": ["sim"]},
    ]


# JS que roda NA página: acha cada campo pelo texto do rótulo e escolhe a
# opção pelo texto. Devolve o relatório do que casou (é o que o probe mostra).
JS_PREENCHER = r"""
(filtros) => {
  const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toLowerCase().replace(/\s+/g, ' ').trim();
  const rotuloDe = el => {
    let t = '';
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) t += ' ' + l.textContent;
    }
    const lab = el.closest('label'); if (lab) t += ' ' + lab.textContent;
    const cel = el.closest('td, th, div, li, span');
    if (cel && cel.previousElementSibling) t += ' ' + cel.previousElementSibling.textContent;
    const tr = el.closest('tr');
    if (tr && tr.cells && tr.cells.length) t += ' ' + tr.cells[0].textContent;
    t += ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.name || '');
    t += ' ' + (el.title || '');
    return norm(t);
  };
  const casaRotulo = (el, rotulos) => {
    const r = rotuloDe(el);
    return rotulos.some(x => r.includes(x));
  };
  const relatorio = [];
  for (const f of filtros) {
    let feito = null;
    // 1) <select> com rótulo casado e opção casada
    for (const s of document.querySelectorAll('select')) {
      const opt = [...s.options].find(
        o => f.opcao.some(x => norm(o.text) === x || norm(o.text).includes(x)));
      if (opt && casaRotulo(s, f.rotulos)) {
        s.value = opt.value; s.dispatchEvent(new Event('change', {bubbles: true}));
        feito = {tipo: 'select', nome: s.name, opcao: opt.text.trim()}; break;
      }
    }
    // 2) rádio/checkbox cujo próprio texto casa a opção, no grupo do rótulo
    if (!feito) {
      for (const i of document.querySelectorAll('input[type=radio], input[type=checkbox]')) {
        const txt = norm((i.closest('label') || {}).textContent || '') + ' ' + norm(i.value);
        const l = i.id ? document.querySelector('label[for="' + CSS.escape(i.id) + '"]') : null;
        const t2 = txt + ' ' + norm(l ? l.textContent : '');
        if (f.opcao.some(x => t2.includes(x)) && casaRotulo(i, f.rotulos)) {
          i.checked = true; i.dispatchEvent(new Event('change', {bubbles: true}));
          i.dispatchEvent(new Event('click', {bubbles: true}));
          feito = {tipo: i.type, nome: i.name, opcao: i.value}; break;
        }
      }
    }
    // 3) campo de texto (o ano às vezes é digitado)
    if (!feito && f.texto) {
      for (const i of document.querySelectorAll('input[type=text], input:not([type])')) {
        if (casaRotulo(i, f.rotulos)) {
          i.value = f.texto; i.dispatchEvent(new Event('change', {bubbles: true}));
          feito = {tipo: 'texto', nome: i.name, opcao: f.texto}; break;
        }
      }
    }
    // 4) sem rótulo casado: um <select> cuja opção é INEQUÍVOCA
    if (!feito && f.chave === 'qualificacao') {
      for (const s of document.querySelectorAll('select')) {
        const opt = [...s.options].find(o => f.opcao.some(x => norm(o.text).includes(x)));
        if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', {bubbles: true}));
          feito = {tipo: 'select', nome: s.name, opcao: opt.text.trim(), sem_rotulo: true}; break; }
      }
    }
    relatorio.push({chave: f.chave, ok: !!feito, ...(feito || {})});
  }
  return relatorio;
}
"""

# Inventário do formulário — só para o probe (calibração).
JS_INVENTARIO = r"""
() => [...document.querySelectorAll('select, input, button')].map(el => {
  const tr = el.closest('tr');
  return {
    tag: el.tagName.toLowerCase(), tipo: el.type || null, nome: el.name || null, id: el.id || null,
    valor: el.tagName === 'SELECT' ? null : (el.value || null),
    linha: tr && tr.cells && tr.cells.length ? tr.cells[0].textContent.trim().slice(0, 80) : null,
    opcoes: el.tagName === 'SELECT' ? [...el.options].map(o => o.text.trim()).slice(0, 25) : null,
  };
}).filter(x => x.tipo !== 'hidden')
"""

JS_SUBMETER = r"""
() => {
  const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const alvos = [...document.querySelectorAll('input[type=submit], input[type=button], button, a')];
  const b = alvos.find(
    el => /^(consultar|pesquisar|buscar|filtrar)$/.test(norm(el.value || el.textContent)));
  if (b) { b.click(); return norm(b.value || b.textContent); }
  const f = document.querySelector('form'); if (f) { f.submit(); return 'form.submit'; }
  return null;
}
"""

JS_PROXIMA = r"""
(clicar) => {
  const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const alvos = document.querySelectorAll('a, input[type=button], input[type=submit], button');
  const a = [...alvos].find(el => {
    const t = norm(el.textContent || el.value || '') + ' ' + norm(el.title || '');
    return /(^|\s)(proxim[ao]|prox\.?|>>?|»)(\s|$)/.test(t);
  });
  if (!a || a.classList.contains('disabled')) return false;
  if (a.getAttribute('aria-disabled') === 'true') return false;
  if (clicar) a.click();
  return true;
}
"""


@dataclass
class Coleta:
    programas: list[dict[str, Any]]
    filtros: list[dict[str, Any]]
    paginas: int
    detalhes: int


async def _abrir_browser(p: Any) -> Any:
    from ..scraping.playwright import ARGS_CHROMIUM, _executavel_do_sistema

    try:
        return await p.chromium.launch(args=ARGS_CHROMIUM)
    except Exception:
        executavel = _executavel_do_sistema()
        if not executavel:
            raise
        return await p.chromium.launch(args=ARGS_CHROMIUM, executable_path=executavel)


async def _consulta_url() -> str:
    from ..services import config as config_service

    return (await config_service.resolver("programas_webapp_url") or "").strip() or CONSULTA


async def _agir(pg: Any, js: str, arg: Any = None, *, espera_ms: int = 30_000) -> Any:
    """Roda uma ação na página e espera a NAVEGAÇÃO que ela dispara, se houver.

    `wait_for_load_state` sozinho volta na hora — o estado "carregado" já era
    verdade ANTES do clique — e o `content()` seguinte pega a página no meio da
    troca ("page is navigating"). `expect_navigation` amarra a espera ao clique;
    ação que não navega (onchange sem submit, AJAX) cai no timeout curto e segue.
    """
    resultado = None
    try:
        async with pg.expect_navigation(wait_until="load", timeout=espera_ms):
            resultado = await pg.evaluate(js, arg) if arg is not None else await pg.evaluate(js)
    except Exception as exc:  # noqa: BLE001 — sem navegação é caminho normal
        if "Timeout" not in type(exc).__name__ and "timeout" not in str(exc).lower():
            raise
    try:
        await pg.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:  # noqa: BLE001 — rede que não sossega não invalida o DOM
        pass
    return resultado


async def _html(pg: Any) -> str:
    """`content()` com nova tentativa enquanto a página ainda está trocando."""
    for _ in range(10):
        try:
            return await pg.content()
        except Exception as exc:  # noqa: BLE001
            if "navigating" not in str(exc):
                raise
            await pg.wait_for_timeout(300)
    return await pg.content()


class ProgramasWebappConnector:
    source_id = SOURCE_ID

    async def coletar(
        self,
        ano: int | None = None,
        *,
        max_paginas: int = MAX_PAGINAS,
        max_detalhes: int = MAX_DETALHES,
        inventario: bool = False,
    ) -> Coleta | dict:
        """Roda a consulta com os três filtros e devolve os programas aptos.

        `inventario=True` para antes de consultar e devolve o formulário como a
        página o desenha — é o modo de calibração do `probe_programas`.
        """
        from playwright.async_api import async_playwright  # import tardio: extra pesado

        ano = ano or datetime.now().year
        consulta = await _consulta_url()
        async with async_playwright() as p:
            browser = await _abrir_browser(p)
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                pg.set_default_timeout(TIMEOUT_MS)
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                await pg.goto(consulta, wait_until="networkidle", timeout=TIMEOUT_MS)
                if "login" in norm(await pg.title()) or "idp." in pg.url:
                    raise RuntimeError(
                        "o acesso livre do Transferegov não abriu a consulta de programas "
                        "(caiu na tela de login) — o rito do guest pode ter mudado"
                    )
                if inventario:
                    return {
                        "url": pg.url,
                        "titulo": await pg.title(),
                        "campos": await pg.evaluate(JS_INVENTARIO),
                    }

                relatorio: list[dict[str, Any]] = []
                for filtro in filtros_padrao(ano):
                    # um filtro por vez: `onchange` pode recarregar o formulário
                    (item,) = await _agir(pg, JS_PREENCHER, [filtro], espera_ms=1_500)
                    relatorio.append(item)
                faltando = [r["chave"] for r in relatorio if not r.get("ok")]
                if faltando:
                    log.warning(
                        "programas_webapp: filtro(s) sem campo casado: %s — calibre com "
                        "`python -m src.tools.probe_programas --formulario`",
                        faltando,
                    )

                if not await _agir(pg, JS_SUBMETER):
                    raise RuntimeError("não achei o botão de consultar do formulário de programas")

                programas: dict[str, dict[str, Any]] = {}
                paginas = 0
                assinaturas: set[str] = set()
                while paginas < max_paginas:
                    tab = tabela_de_programas(await _html(pg))
                    if tab is None:
                        break
                    assinatura = "|".join(str(r) for r in tab.linhas[:2])
                    if assinatura in assinaturas:  # "próxima" que não avança
                        break
                    assinaturas.add(assinatura)
                    paginas += 1
                    for linha in tab.linhas:
                        prog = programa_da_linha(linha)
                        if prog:
                            chave = prog["id_programa"] or prog["codigo"] or prog["nome"]
                            programas.setdefault(chave, prog)
                    # olha antes de clicar: sem "próxima", esperar a navegação
                    # que o clique dispararia custaria o timeout inteiro
                    if not await pg.evaluate(JS_PROXIMA, False):
                        break
                    await _agir(pg, JS_PROXIMA, True)

                if paginas == 0:
                    raise RuntimeError(
                        "a consulta de programas não devolveu tabela de resultado — "
                        "o layout pode ter mudado (rode o probe_programas)"
                    )

                # a ficha completa só para o que a lista não disse: UF,
                # natureza e as janelas são o que decide "pode se inscrever"
                detalhes = 0
                for prog in programas.values():
                    if detalhes >= max_detalhes or not prog.get("url_detalhe"):
                        continue
                    if prog.get("ufs") and prog.get("naturezas") and prog.get("fim_proposta"):
                        continue
                    try:
                        await pg.goto(prog["url_detalhe"], wait_until="networkidle")
                        extra = detalhe_do_programa(await _html(pg))
                    except Exception:  # noqa: BLE001 — uma ficha não derruba a coleta
                        log.warning("programas_webapp: ficha falhou: %s", prog["url_detalhe"])
                        continue
                    detalhes += 1
                    for k, v in extra.items():
                        if not prog.get(k):
                            prog[k] = v
                    if not prog.get("id_programa"):
                        m = _ID_PROGRAMA.search(pg.url)
                        prog["id_programa"] = m.group(1) if m else None

                return Coleta(
                    programas=list(programas.values()),
                    filtros=relatorio,
                    paginas=paginas,
                    detalhes=detalhes,
                )
            finally:
                await browser.close()

    async def health_check(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except Exception:
            return False
        return True
