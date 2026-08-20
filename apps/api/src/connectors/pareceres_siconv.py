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

TIMEOUT_MS = 60_000
MAX_PARECERES = 30  # trava: uma proposta não tem centenas de pareceres

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
