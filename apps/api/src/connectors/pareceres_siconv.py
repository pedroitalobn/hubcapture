"""Pareceres de proposta DISCRICIONÁRIA/legal — webapp do SIconv, acesso livre.

O pacote diário do SIconv não publica parecer nenhum, e a API do módulo
especiais só conhece as transferências especiais. O parecer da proposta
discricionária mora no webapp antigo (Struts) em
`discricionarias.transferegov.sistema.gov.br/voluntarias`, atrás do SSO do
Transferegov — mas a consulta pública continua existindo: a entrada com
`Usr=guest&Pwd=guest` (a mesma dos links "Acesso Livre" do portal gov.br)
estabelece sessão anônima e as páginas `.do` respondem.

POR QUE BROWSER, e não httpx: o SSO devolve um formulário de auto-post SAML
que depende de JS; reproduzi-lo na mão terminou em 401 (testado — o IdP recusa
o guest fora do fluxo do browser). O host NÃO tem Cloudflare, então o Chromium
LOCAL passa — é o caso oposto ao de `_egress` (lá o bloqueio é do IP; aqui é
só o rito do SSO).

O rito, na ordem (a sessão guarda a proposta em memória — o detalhe PRECISA
ser visitado antes da aba, senão a lista vem vazia):
  1. `ForwardAction.do?...&Usr=guest&Pwd=guest` → sessão anônima;
  2. `ResultadoDaConsultaDePropostaDetalharProposta.do?idProposta=<id>`;
  3. `ForwardAction.do?modulo=proposta&path=/SelecionarObjeto/SelecionarObjeto.do?destino=DetalharParecerProposta`
     → lista com os `idParecer`;
  4. `ParecerPropostaVisualizarParecer.do?idProposta=<id>&idParecer=<idp>`
     → a página de UM parecer, com o texto.

A chave é o `idProposta` INTERNO do SIconv (o mesmo `ID_PROPOSTA` do pacote
diário — vem em `propostas.id_externo` nas cargas `siconv:pacote-diario`).
"""

from __future__ import annotations

import html as html_
import logging
import re

log = logging.getLogger(__name__)

SOURCE_ID = "siconv_parecer"
SOURCE_ID_EMPENHO = "siconv_webapp_empenho"

BASE = "https://discricionarias.transferegov.sistema.gov.br/voluntarias"
ENTRADA = (
    f"{BASE}/ForwardAction.do?modulo=Principal"
    "&path=/MostraPrincipalConsultarProposta.do&Usr=guest&Pwd=guest"
)
DETALHE = f"{BASE}/ConsultarProposta/ResultadoDaConsultaDePropostaDetalharProposta.do"
ABA_PARECERES = (
    f"{BASE}/ForwardAction.do?modulo=proposta"
    "&path=/SelecionarObjeto/SelecionarObjeto.do?destino=DetalharParecerProposta"
)
VISUALIZAR = f"{BASE}/DetalharParecerProposta/ParecerPropostaVisualizarParecer.do"
ABA_EMPENHOS = (
    f"{BASE}/ForwardAction.do?modulo=proposta"
    "&path=/SelecionarObjeto/SelecionarObjeto.do?destino=ManterEmpenhoNovoSiafi"
)
ABA_REPASSES = (
    f"{BASE}/ForwardAction.do?modulo=proposta"
    "&path=/SelecionarConvenio/SelecionarConvenio.do?destino=ListarRepasses"
)

TIMEOUT_MS = 60_000
MAX_PARECERES = 30  # trava: uma proposta não tem centenas de pareceres
MAX_DOCUMENTOS = 60  # idem para a lista de documentos digitalizados
SOURCE_ID_DOCUMENTO = "siconv_documento"

# Os rótulos da página, na ordem em que aparecem. O TEXTO do parecer não está
# aqui: ele mora num `<textarea name="parecer">`, que o inner_text da página
# NÃO inclui (custou uma rodada de "layout não casou") — vem à parte, do DOM.
_RE_CAMPOS = re.compile(
    r"Data\s+(?P<data>\d{2}/\d{2}/\d{4})\s+"
    r"Parecer do\s+(?P<esfera>.+?)\s+"
    r"Responsável\s+(?P<responsavel>.+?)\s+"
    r"Atribuição\s+(?P<papel>.+?)\s+"
    r"Função\s+(?P<cargo>.+?)\s+Parecer\b",
    re.S,
)


def _parse_parecer(corpo: str, texto: str, id_proposta: str, id_parecer: str) -> dict | None:
    """Campos do parecer: rótulos visíveis + o texto vindo do textarea.

    Página Struts sem ids nos elementos: o casamento é pelos rótulos visíveis,
    que são estáveis há anos nesse sistema. Se o layout mudar a ponto de o
    regex não casar, devolve None e o chamador registra a página como perdida
    em vez de gravar um parecer pela metade.
    """
    plano = re.sub(r"\s+", " ", corpo)
    m = _RE_CAMPOS.search(plano)
    if not m:
        return None
    campos = {k: v.strip() for k, v in m.groupdict().items()}
    campos["texto"] = " ".join((texto or "").split())
    if not campos["texto"]:
        return None
    return {
        "id_parecer": f"{id_proposta}:{id_parecer}",
        "data": campos["data"],
        "esfera": campos["esfera"],
        "responsavel": campos["responsavel"],
        "papel": campos["papel"],
        "cargo": campos["cargo"],
        "texto": campos["texto"],
        "url_parecer": f"{VISUALIZAR}?idProposta={id_proposta}&idParecer={id_parecer}",
        "_scraper": "playwright",  # proveniência: veio da página, não de API
    }


# Linha da "Listagem de Notas de Empenho" (texto da página): número NE, minuta,
# dois valores em R$ (empenho e empenho no SIAFI), situação e data de emissão.
_RE_EMPENHO = re.compile(
    r"(?P<numero>\d{4}NE\d{6})\s+"
    r"(?P<minuta>\d+)\s+"
    r"R\$\s*(?P<valor>[\d.]+,\d{2})\s+"
    r"R\$\s*(?P<valor_siafi>[\d.]+,\d{2})\s+"
    r"(?P<situacao>.+?)\s+"
    r"(?P<data>\d{2}/\d{2}/\d{4})"
)


# Cabeçalho do detalhe do instrumento — os rótulos que respondem as três
# perguntas do gestor (empenhou? publicou? pagou?) mais a referência SIAFI.
_RE_EXECUCAO = (
    (
        "situacao_instrumento",
        re.compile(
            r"Situação\s+(?!no SIAFI|de Contratação)([A-Za-zÀ-ú ]{3,40}?)\s+Empenhado\b"
        ),
    ),
    ("empenhado_flag", re.compile(r"Empenhado\s+(sim|não)\b", re.I)),
    ("situacao_siafi", re.compile(r"Situação no SIAFI\s+(.{3,60}?)\s+Subtipo")),
    ("instrumento", re.compile(r"Código do Instrumento\s+(\d+)")),
    ("processo", re.compile(r"Número do Processo\s+(\S+)")),
)

# A PUBLICAÇÃO sai por caminho próprio (ponto 09). O rótulo "Publicação" aparece
# mais de uma vez na página (a lista de documentos tem um arquivo chamado
# "Publicação…"), e o primeiro casamento podia trazer o valor do campo VIZINHO
# — o `sim` do "Empenhado sim" ao lado. Percorremos TODOS os casamentos e
# ficamos com o primeiro que é resposta a "saiu ou não saiu?"; nenhum sendo,
# não gravamos nada, que é melhor que gravar a resposta de outra pergunta.
_RE_PUBLICACAO = re.compile(
    r"Publicaç(?:ão|ao)\s+([A-Za-zÀ-ú/0-9 ]{2,40}?)\s+(?:Regime|Código|Situação|Número|Data)"
)


def _situacao_publicacao(plano: str) -> str | None:
    from ..services import publicacao

    for m in _RE_PUBLICACAO.finditer(plano):
        valor = m.group(1).strip()
        if publicacao.estado(valor) != publicacao.SEM_INFORMACAO:
            return valor
    return None

# Resumo da "Listagem de Repasses": total, desembolsado (o PAGO de verdade),
# a desembolsar e a data do último desembolso (ausente quando nada saiu).
_RE_REPASSES = re.compile(
    r"Valor Total de Repasse \(R\$\)\s*Valor Desembolsado \(R\$\)\s*"
    r"Valor a desembolsar \(R\$\)\s*Data do último desembolso\s*"
    r"R\$\s*(?P<total>[\d.]+,\d{2})\s*R\$\s*(?P<pago>[\d.]+,\d{2})\s*"
    r"R\$\s*(?P<a_pagar>[\d.]+,\d{2})\s*(?P<ultimo>\d{2}/\d{2}/\d{4})?"
)


def _parse_execucao(corpo: str) -> dict:
    plano = re.sub(r"\s+", " ", corpo)
    saida = {}
    for chave, rx in _RE_EXECUCAO:
        m = rx.search(plano)
        if m:
            saida[chave] = m.group(1).strip()
    publicacao = _situacao_publicacao(plano)
    if publicacao:
        saida["situacao_publicacao"] = publicacao
    return saida


def _parse_repasses(corpo: str) -> dict:
    m = _RE_REPASSES.search(re.sub(r"\s+", " ", corpo))
    if not m:
        return {}
    c = m.groupdict()
    return {
        "valor_repasse_total": c["total"],
        "valor_desembolsado": c["pago"],
        "valor_a_desembolsar": c["a_pagar"],
        "data_ultimo_desembolso": c["ultimo"],
    }


# ── Lista de Documentos Digitalizados ──────────────────────────────────────
# O arquivo que comprova o ato (a publicação, o contrato assinado, o ofício ao
# legislativo) está NA MESMA página de detalhe que já visitamos — no fim, numa
# tabela "Nome Arquivo | Data Upload | Baixar". Não custa navegação nova.
#
# O parse é do HTML e não do inner_text porque o que interessa junto do nome é
# o LINK: sem ele o gestor lê que o documento existe e continua sem o documento.
_MARCA_DOCUMENTOS = re.compile(r"documentos?\s+digitalizados?", re.I)
_LINHA = re.compile(r"<tr\b.*?</tr>", re.I | re.S)
_CELULA = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_DATA_BR = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_HREF = re.compile(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I)
_ACAO_JS = re.compile(r"""['"]([^'"]*\.do\?[^'"]+)['"]""", re.I)


def _texto_da_celula(html_bruto: str) -> str:
    return " ".join(html_.unescape(_TAGS.sub(" ", html_bruto)).split())


def _url_da_linha(linha: str) -> str | None:
    """O link de download da linha, absoluto. Âncora morta (`#`, `javascript:`)
    não conta como link: o alvo real, nessas páginas, vem no onclick."""
    for bruto in _HREF.findall(linha):
        alvo = bruto.strip()
        if alvo and not alvo.startswith("#") and not alvo.lower().startswith("javascript:"):
            return _absoluta(alvo)
    m = _ACAO_JS.search(linha)
    return _absoluta(m.group(1)) if m else None


def _absoluta(alvo: str) -> str:
    if alvo.startswith("http"):
        return alvo
    return f"{BASE}/{alvo.lstrip('/')}"


def parse_documentos(html_pagina: str) -> list[dict]:
    """Linhas da lista de documentos digitalizados da página de detalhe.

    Tolerante de propósito: a tabela é Struts de 2004, sem id nem classe. O que
    define uma linha VÁLIDA é ter um nome de arquivo e uma data — cabeçalho,
    rodapé e "Nenhum registro" não têm as duas coisas e caem fora sozinhos.
    """
    marca = _MARCA_DOCUMENTOS.search(html_pagina)
    if not marca:
        return []
    trecho = html_pagina[marca.end() :]
    saida: list[dict] = []
    for linha in _LINHA.findall(trecho):
        celulas = [_texto_da_celula(c) for c in _CELULA.findall(linha)]
        celulas = [c for c in celulas if c]
        if len(celulas) < 2:
            continue
        datas = [c for c in celulas if _DATA_BR.fullmatch(c)]
        if not datas:
            continue
        # o nome é a célula mais longa que não é data nem rótulo de botão
        candidatos = [
            c
            for c in celulas
            if not _DATA_BR.fullmatch(c) and c.lower() not in ("baixar", "detalhar", "excluir")
        ]
        if not candidatos:
            continue
        nome = max(candidatos, key=len)
        saida.append(
            {
                "nome": nome,
                "data_upload": datas[0],
                "url": _url_da_linha(linha),
                "_scraper": "playwright",
            }
        )
        if len(saida) >= MAX_DOCUMENTOS:
            break
    return saida


class ParecerSiconvConnector:
    source_id = SOURCE_ID

    async def collect_por_id_proposta(self, id_proposta: str) -> list[dict]:
        """Todos os pareceres da proposta, com texto — via sessão anônima."""
        id_proposta = str(id_proposta).strip()
        if not id_proposta.isdigit():
            raise ValueError(
                f"idProposta do SIconv deve ser o id numérico interno (veio {id_proposta!r})"
            )
        from playwright.async_api import async_playwright  # import tardio: extra pesado

        saida: list[dict] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                await pg.goto(
                    f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio=",
                    wait_until="networkidle",
                    timeout=TIMEOUT_MS,
                )
                if "Login" in (await pg.title()):
                    raise RuntimeError(
                        "o acesso livre do Transferegov não abriu a proposta "
                        "(caiu na tela de login) — o rito do guest pode ter mudado"
                    )
                await pg.goto(ABA_PARECERES, wait_until="networkidle", timeout=TIMEOUT_MS)
                ids = sorted(
                    set(re.findall(r"idParecer=(\d+)", html_.unescape(await pg.content())))
                )[:MAX_PARECERES]
                for idp in ids:
                    await pg.goto(
                        f"{VISUALIZAR}?idProposta={id_proposta}&idParecer={idp}",
                        wait_until="networkidle",
                        timeout=TIMEOUT_MS,
                    )
                    try:
                        texto = await pg.eval_on_selector(
                            "textarea[name=parecer]", "el => el.value"
                        )
                    except Exception:  # noqa: BLE001 — sem textarea = sem texto
                        texto = ""
                    parecer = _parse_parecer(
                        await pg.inner_text("body"), texto, id_proposta, idp
                    )
                    if parecer:
                        saida.append(parecer)
                    else:
                        log.warning(
                            "siconv_parecer: página do parecer %s/%s não casou o layout",
                            id_proposta,
                            idp,
                        )
            finally:
                await browser.close()
        return saida

    async def empenhos_por_id_proposta(self, id_proposta: str) -> list[dict]:
        """Notas de empenho da proposta — a listagem VIVA do webapp.

        O pacote diário também traz empenho, mas o espelho público é atualizado
        ~mensalmente: empenho emitido depois do dump só existe aqui. Mesmo rito
        de sessão dos pareceres; a aba `ManterEmpenhoNovoSiafi` encaminha para
        o JSF `listarEmpenhosNovoSiafi.jsf` já no contexto da proposta.
        """
        id_proposta = str(id_proposta).strip()
        if not id_proposta.isdigit():
            raise ValueError(
                f"idProposta do SIconv deve ser o id numérico interno (veio {id_proposta!r})"
            )
        from playwright.async_api import async_playwright

        saida: list[dict] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                await pg.goto(
                    f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio=",
                    wait_until="networkidle",
                    timeout=TIMEOUT_MS,
                )
                if "Login" in (await pg.title()):
                    raise RuntimeError(
                        "o acesso livre do Transferegov não abriu a proposta "
                        "(caiu na tela de login) — o rito do guest pode ter mudado"
                    )
                await pg.goto(ABA_EMPENHOS, wait_until="networkidle", timeout=TIMEOUT_MS)
                corpo = re.sub(r"\s+", " ", await pg.inner_text("body"))
                for m in _RE_EMPENHO.finditer(corpo):
                    c = m.groupdict()
                    saida.append(
                        {
                            "id_empenho": f"{id_proposta}:{c['numero']}",
                            "numero_empenho": c["numero"],
                            "numero_minuta": c["minuta"],
                            "valor_empenho": c["valor"],
                            "valor_empenho_siafi": c["valor_siafi"],
                            "situacao": c["situacao"],
                            "data_emissao": c["data"],
                            "_scraper": "playwright",
                        }
                    )
            finally:
                await browser.close()
        return saida

    async def documentos_por_id_proposta(self, id_proposta: str) -> list[dict]:
        """Documentos digitalizados da proposta — a lista da própria página de
        detalhe (publicação, contrato assinado, ofício ao legislativo).

        Mesmo rito de sessão dos pareceres. Não há aba a visitar: a tabela vive
        no fim do detalhe, então a página que já abrimos basta.
        """
        id_proposta = str(id_proposta).strip()
        if not id_proposta.isdigit():
            raise ValueError(
                f"idProposta do SIconv deve ser o id numérico interno (veio {id_proposta!r})"
            )
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                await pg.goto(
                    f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio=",
                    wait_until="networkidle",
                    timeout=TIMEOUT_MS,
                )
                if "Login" in (await pg.title()):
                    raise RuntimeError(
                        "o acesso livre do Transferegov não abriu a proposta "
                        "(caiu na tela de login) — o rito do guest pode ter mudado"
                    )
                return parse_documentos(await pg.content())
            finally:
                await browser.close()

    async def coletar_lote(
        self, ids_proposta: list[str], *, incluir_empenhos: bool = True
    ) -> dict[str, dict]:
        """Pareceres (e empenhos) de VÁRIAS propostas numa sessão de browser só.

        O rito de sessão (entrada guest + SSO) custa ~5 s; pagá-lo por proposta
        transformaria o sweep noturno em horas de browser. Aqui a entrada
        acontece UMA vez e as propostas passam em série pela mesma sessão —
        o webapp guarda "a proposta corrente" por sessão, então o detalhe de
        cada uma é visitado antes das suas abas, como no caminho unitário.

        Falha em uma proposta não derruba o lote: o item sai do resultado com
        `erro` preenchido e o chamador decide (registrar e seguir).
        """
        from playwright.async_api import async_playwright

        resultado: dict[str, dict] = {}
        alvos = [str(i).strip() for i in ids_proposta if str(i).strip().isdigit()]
        if not alvos:
            return resultado
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                for id_proposta in alvos:
                    item: dict = {
                        "pareceres": [],
                        "empenhos": [],
                        "documentos": [],
                        "execucao": {},
                        "repasses": {},
                        "erro": None,
                    }
                    resultado[id_proposta] = item
                    try:
                        await pg.goto(
                            f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio=",
                            wait_until="networkidle",
                            timeout=TIMEOUT_MS,
                        )
                        if "Login" in (await pg.title()):
                            raise RuntimeError("sessão de acesso livre caiu no login")
                        item["execucao"] = _parse_execucao(await pg.inner_text("body"))
                        # a lista de documentos está NESTA página — de graça
                        item["documentos"] = parse_documentos(await pg.content())
                        await pg.goto(
                            ABA_PARECERES, wait_until="networkidle", timeout=TIMEOUT_MS
                        )
                        ids = sorted(
                            set(
                                re.findall(
                                    r"idParecer=(\d+)",
                                    html_.unescape(await pg.content()),
                                )
                            )
                        )[:MAX_PARECERES]
                        for idp in ids:
                            await pg.goto(
                                f"{VISUALIZAR}?idProposta={id_proposta}&idParecer={idp}",
                                wait_until="networkidle",
                                timeout=TIMEOUT_MS,
                            )
                            try:
                                texto = await pg.eval_on_selector(
                                    "textarea[name=parecer]", "el => el.value"
                                )
                            except Exception:  # noqa: BLE001
                                texto = ""
                            parecer = _parse_parecer(
                                await pg.inner_text("body"), texto, id_proposta, idp
                            )
                            if parecer:
                                item["pareceres"].append(parecer)
                        if incluir_empenhos:
                            # volta ao contexto da proposta antes da outra aba
                            await pg.goto(
                                f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio=",
                                wait_until="networkidle",
                                timeout=TIMEOUT_MS,
                            )
                            await pg.goto(
                                ABA_EMPENHOS, wait_until="networkidle", timeout=TIMEOUT_MS
                            )
                            corpo = re.sub(r"\s+", " ", await pg.inner_text("body"))
                            for m in _RE_EMPENHO.finditer(corpo):
                                c = m.groupdict()
                                item["empenhos"].append(
                                    {
                                        "id_empenho": f"{id_proposta}:{c['numero']}",
                                        "numero_empenho": c["numero"],
                                        "numero_minuta": c["minuta"],
                                        "valor_empenho": c["valor"],
                                        "valor_empenho_siafi": c["valor_siafi"],
                                        "situacao": c["situacao"],
                                        "data_emissao": c["data"],
                                        "_scraper": "playwright",
                                    }
                                )
                            # o PAGO de verdade mora na listagem de repasses do
                            # instrumento (desembolso ao convenente) — o pacote
                            # público só o publica ~mensalmente
                            await pg.goto(
                                ABA_REPASSES, wait_until="networkidle", timeout=TIMEOUT_MS
                            )
                            item["repasses"] = _parse_repasses(
                                await pg.inner_text("body")
                            )
                    except Exception as exc:  # noqa: BLE001 — uma proposta não derruba o lote
                        item["erro"] = f"{type(exc).__name__}: {exc}"
                        log.warning(
                            "siconv lote: proposta %s falhou: %s", id_proposta, item["erro"]
                        )
            finally:
                await browser.close()
        return resultado

    async def health_check(self) -> bool:
        """Saudável = a entrada anônima responde fora da tela de login."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                try:
                    pg = await (await browser.new_context()).new_page()
                    await pg.goto(ENTRADA, wait_until="networkidle", timeout=30_000)
                    return "Login" not in (await pg.title())
                finally:
                    await browser.close()
        except Exception:  # noqa: BLE001 — health nunca levanta
            return False


def get_connector() -> ParecerSiconvConnector:
    return ParecerSiconvConnector()
