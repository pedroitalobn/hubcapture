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
import unicodedata
from urllib.parse import parse_qsl, unquote, urljoin, urlparse, urlunparse

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
MAX_DOCUMENTOS = 300  # idem para a lista de documentos digitalizados (pode paginar)
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
        re.compile(r"Situação\s+(?!no SIAFI|de Contratação)([A-Za-zÀ-ú ]{3,40}?)\s+Empenhado\b"),
    ),
    ("empenhado_flag", re.compile(r"Empenhado\s+(sim|não)\b", re.I)),
    ("situacao_siafi", re.compile(r"Situação no SIAFI\s+(.{3,60}?)\s+Subtipo")),
    ("instrumento", re.compile(r"Código do Instrumento\s+(\d+)")),
    ("processo", re.compile(r"Número do Processo\s+(\S+)")),
)

# A PUBLICAÇÃO sai por caminho próprio, e agora ESTRUTURAL: o dado é o campo
# "Publicação" dos DADOS DA PROPOSTA, e é assim que ele tem de ser lido.
#
# Ler o texto corrido da página é o que produzia o falso positivo. O rótulo
# aparece mais de uma vez — a lista de documentos digitalizados tem arquivos
# chamados "Publicação…" —, e uma varredura livre podia devolver ora o valor do
# campo VIZINHO (o `sim` do "Empenhado sim"), ora o NOME de um arquivo cujo
# título contém "publicado". Nos dois casos o Hub afirmava publicação que o
# portal desmentia.
#
# Então: casamos o RÓTULO da célula com o valor da célula seguinte (é uma
# tabela de rótulo→valor, mesmo sendo Struts de 2004) e só aceitamos o rótulo
# EXATO do campo. Nome de arquivo é valor de célula, nunca rótulo — sozinho
# isto já mata o falso positivo. O texto corrido continua como retaguarda para
# o caso de o layout mudar, mas recortado ANTES da lista de documentos.
_ROTULOS_PUBLICACAO = (
    "publicacao",
    "situacao da publicacao",
    "situacao publicacao",
)

_RE_PUBLICACAO = re.compile(
    r"Publicaç(?:ão|ao)\s+([A-Za-zÀ-ú/0-9 ]{2,40}?)\s+(?:Regime|Código|Situação|Número|Data)"
)


def _rotulo(texto: str) -> str:
    """Rótulo de célula normalizado para comparação (sem acento, sem pontuação)."""
    plano = unicodedata.normalize("NFD", texto.strip().lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s:*.]+", " ", plano).strip()


def _antes_dos_documentos(conteudo: str) -> str:
    """O trecho que é a FICHA da proposta — a lista de documentos fica de fora.

    O que vem depois desta marca é acervo de arquivos: nome de documento não
    responde "saiu ou não saiu?", por mais que comece com "Publicação".
    """
    marca = _MARCA_DOCUMENTOS.search(conteudo)
    return conteudo[: marca.start()] if marca else conteudo


def _campo_rotulado(html_pagina: str, rotulos: tuple[str, ...]) -> str | None:
    """Valor da célula seguinte ao rótulo EXATO, na ficha da proposta."""
    for linha in _LINHA.findall(_antes_dos_documentos(html_pagina)):
        celulas = [_texto_da_celula(c) for c in _CELULA.findall(linha)]
        for i, celula in enumerate(celulas[:-1]):
            if _rotulo(celula) in rotulos:
                valor = celulas[i + 1].strip()
                if valor:
                    return valor
    return None


def _situacao_publicacao(plano: str, html_pagina: str | None = None) -> str | None:
    """A situação da publicação como a fonte a declara — ou nada.

    Nada é resposta: sem o campo, o Hub diz "sem informação na fonte" e o gestor
    confere no portal. É melhor que herdar a resposta de outra pergunta.
    """
    from ..services import publicacao

    if html_pagina:
        valor = _campo_rotulado(html_pagina, _ROTULOS_PUBLICACAO)
        if valor and publicacao.estado(valor) != publicacao.SEM_INFORMACAO:
            return valor
        if valor:
            log.warning(
                "siconv: campo Publicação com valor não reconhecido (%r) — "
                "não gravado; calibrar em _situacao_publicacao",
                valor[:80],
            )
            return None
    for m in _RE_PUBLICACAO.finditer(_antes_dos_documentos(plano)):
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


def _parse_execucao(corpo: str, html_pagina: str | None = None) -> dict:
    """Cabeçalho do instrumento. A publicação vem do HTML quando ele existe —
    é o único jeito de saber que o valor lido é o do CAMPO, e não texto vizinho."""
    plano = re.sub(r"\s+", " ", corpo)
    saida = {}
    for chave, rx in _RE_EXECUCAO:
        m = rx.search(plano)
        if m:
            saida[chave] = m.group(1).strip()
    publicacao = _situacao_publicacao(plano, html_pagina)
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
_ANCORA = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
# a data pode vir com hora ("22/06/2026 14:32") — o grupo 1 é só a data
_DATA_BR = re.compile(r"\b(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b")
_HREF = re.compile(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I)
# qualquer string entre aspas que aponte para uma ação Struts (`.do`), COM ou
# SEM query — o onclick da página varia: baixar('X.do?id=1'), window.open("X.do"),
# location.href='X.do?id=1'. A versão anterior exigia `.do?` e perdia as demais.
_ACAO_JS = re.compile(r"""['"]([^'"]*\.do(?:\?[^'"]*)?)['"]""", re.I)
# id numérico solto na linha: `<input type=hidden name="idArquivo" value="123">`
# ou `baixarArquivo(123)` / `download('123')` — sem ação nenhuma escrita
_HIDDEN_ID = re.compile(
    r"""<input\b[^>]*name\s*=\s*['"]id\w*['"][^>]*value\s*=\s*['"](\d{1,12})['"]""", re.I
)
_ID_NUMERICO = re.compile(
    r"""\b(?:id(?:Arquivo|Documento|Anexo)?|arquivo|documento|anexo|baixar\w*|download\w*)"""
    r"""\s*[=:(]\s*['"]?(\d{1,12})\b""",
    re.I,
)
#: a ação de download que o webapp usa para o documento da proposta (§56e —
#: é onde o gestor aterrissava no IdP). Retaguarda para a linha que só publica
#: o id do arquivo, sem escrever a ação.
ACAO_BAIXAR = f"{BASE}/EditarDadosProposta/DetalharPropostaBaixar.do?id="
# ordem de preferência entre alvos da mesma linha: o que fala em BAIXAR vence o
# que fala em arquivo (o "Detalhar" do arquivo também fala em arquivo)
_PREFERENCIA_ALVO = (re.compile(r"baix|download", re.I), re.compile(r"arquivo|anexo", re.I))
_ROTULOS_BOTAO = {"baixar", "detalhar", "excluir", "download", "visualizar", "abrir", "ver"}


def _texto_da_celula(html_bruto: str) -> str:
    return " ".join(html_.unescape(_TAGS.sub(" ", html_bruto)).split())


def _alvos_da_linha(linha: str) -> list[str]:
    """Todos os alvos de navegação da linha — hrefs vivos e ações nos scripts.

    `html.unescape` ANTES de ler: no atributo, o `&` vem como `&amp;`, e uma
    URL com dois parâmetros (`?id=1&amp;tipo=2`) mandada crua chega ao Struts
    com o parâmetro `amp;tipo` — o download "falhava" só nas linhas com mais
    de um parâmetro, e ninguém via por quê.
    """
    alvos: list[str] = []
    for bruto in _HREF.findall(linha):
        alvo = html_.unescape(bruto).strip()
        if alvo and not alvo.startswith("#") and not alvo.lower().startswith("javascript:"):
            alvos.append(alvo)
    for bruto in _ACAO_JS.findall(html_.unescape(linha)):
        alvo = bruto.strip()
        if alvo and alvo not in alvos:
            alvos.append(alvo)
    return alvos


def _url_da_linha(linha: str) -> tuple[str | None, bool]:
    """O link de download da linha, absoluto, e se ele foi DERIVADO.

    Âncora morta (`#`, `javascript:`) não conta: o alvo real, nessas páginas,
    vem no onclick. Havendo mais de um alvo (o botão "Detalhar" ao lado do
    "Baixar"), fica o que fala de download. Sem ação escrita mas com o id do
    arquivo à vista, a ação conhecida do webapp é montada — marcada como
    derivada, para a calibração distinguir o que a página disse do que o Hub
    inferiu.
    """
    alvos = _alvos_da_linha(linha)
    if alvos:
        for padrao in _PREFERENCIA_ALVO:
            preferidos = [a for a in alvos if padrao.search(a)]
            if preferidos:
                return _absoluta(preferidos[0]), False
        return _absoluta(alvos[0]), False
    m = _HIDDEN_ID.search(linha) or _ID_NUMERICO.search(html_.unescape(linha))
    if m:
        return ACAO_BAIXAR + m.group(1), True
    return None, False


def _absoluta(alvo: str) -> str:
    """Resolve o href da linha contra a base — pela RFC, não por concatenação.

    O href de download vem absoluto no host (`/voluntarias/EditarDadosProposta/
    DetalharPropostaBaixar.do?id=…`) e a concatenação com a base, que já termina
    em `/voluntarias`, produzia `/voluntarias/voluntarias/…`: o botão "Baixar"
    apontava para uma URL que não existe. `urljoin` trata a barra inicial como
    raiz do host e o relativo puro como irmão da base.
    """
    if alvo.startswith("http"):
        return alvo
    return urljoin(f"{BASE}/", alvo)


#: extensões que fazem de um texto o NOME DE UM ARQUIVO.
_EXTENSAO_ARQUIVO = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|odp|rtf|txt|csv|xml|json|zip|rar|7z|gz|tar"
    r"|p7s|p7m|jpe?g|png|tiff?|gif|bmp|webp|heic|dwg|dxf|kmz|kml|shp|mp4|mp3)\s*$",
    re.I,
)


def e_documento(nome: str, url: str | None) -> bool:
    """A linha é um ARQUIVO, ou é outro campo da ficha que por acaso tem data?

    "nome + data" não basta: a página segue com campos como "Data da Proposta"
    e "Data Início de Vigência", que casam o mesmo formato e entravam na lista
    como se fossem documentos — a seção anunciava "5 arquivos na fonte" com
    quatro deles marcados "sem link na fonte", porque não eram arquivos.
    Documento é o que se BAIXA: tem link de download, ou o nome traz extensão.
    """
    return bool(url) or bool(_EXTENSAO_ARQUIVO.search(nome or ""))


def _escolher_nome(candidatos: list[str]) -> str:
    """O nome do arquivo: a célula com EXTENSÃO; sem ela, a mais longa.

    "Mais longa" sozinha pegava a coluna de descrição quando a tabela a tinha,
    e o gestor pedia ao órgão um arquivo pelo texto errado.
    """
    com_extensao = [c for c in candidatos if _EXTENSAO_ARQUIVO.search(c)]
    return max(com_extensao or candidatos, key=len)


def parse_documentos(html_pagina: str) -> list[dict]:
    """Linhas da lista de documentos digitalizados da página de detalhe.

    Tolerante de propósito: a tabela é Struts de 2004, sem id nem classe —
    cabeçalho, rodapé e "Nenhum registro" caem fora por não serem arquivo.
    O que separa documento de campo-com-data é `e_documento`; linha SEM data
    só entra quando o nome é inequivocamente um arquivo (tem extensão) — a
    exigência de data descartava documento cuja data a página não mostra, e
    afrouxá-la sem essa trava transformaria o "2" da paginação em documento.
    """
    marca = _MARCA_DOCUMENTOS.search(html_pagina)
    if not marca:
        return []
    trecho = html_pagina[marca.end() :]
    saida: list[dict] = []
    for linha in _LINHA.findall(trecho):
        celulas = [c for c in (_texto_da_celula(x) for x in _CELULA.findall(linha)) if c]
        if not celulas:
            continue
        datas = [m.group(1) for m in (_DATA_BR.fullmatch(c) for c in celulas) if m]
        candidatos = [
            c
            for c in celulas
            if not _DATA_BR.fullmatch(c) and c.lower().strip(" .:") not in _ROTULOS_BOTAO
        ]
        if not candidatos:
            continue
        nome = _escolher_nome(candidatos)
        url, derivada = _url_da_linha(linha)
        if datas:
            if not e_documento(nome, url):
                continue
        elif not _EXTENSAO_ARQUIVO.search(nome):
            continue
        item = {
            "nome": nome,
            "data_upload": datas[0] if datas else None,
            "url": url,
            "_scraper": "playwright",
        }
        if derivada:
            item["_url_derivada"] = True
        saida.append(item)
        if len(saida) >= MAX_DOCUMENTOS:
            break
    return saida


# ── Paginação da lista ────────────────────────────────────────────────────────
# A lista Struts pagina (10–20 por página). Ler só a primeira era entregar ao
# gestor uma fração dos arquivos e chamar de "documentos da proposta".
_PAGINACAO_PARAM = re.compile(
    r"(?:^|[?&])(?:pagina|page|numeroPagina|paginaAtual|inicio|offset|pag|indice)=\d+", re.I
)
_TEXTO_PAGINACAO = re.compile(r"^(\d{1,3}|pr[óo]xim[ao]s?|>{1,2}|»|[úu]ltim[ao]s?)$", re.I)
MAX_PAGINAS_DOCUMENTOS = 30


def links_de_paginacao(html_pagina: str) -> list[str]:
    """Links de OUTRAS páginas da lista de documentos, absolutos, sem repetição.

    Entra o link cujo alvo carrega parâmetro de paginação, ou cujo texto é o de
    um paginador ("2", "Próxima", "»") apontando para uma ação Struts. Texto
    numérico sozinho não basta — "2" também é um número de qualquer célula.
    """
    marca = _MARCA_DOCUMENTOS.search(html_pagina)
    if not marca:
        return []
    saida: list[str] = []
    for attrs, texto_html in _ANCORA.findall(html_pagina[marca.end() :]):
        texto = _texto_da_celula(texto_html)
        alvos = _alvos_da_linha(attrs)
        if not alvos:
            continue
        alvo = alvos[0]
        if not (
            _PAGINACAO_PARAM.search(alvo)
            or (_TEXTO_PAGINACAO.match(texto) and ".do" in alvo.lower())
        ):
            continue
        absoluta = _absoluta(alvo)
        if absoluta not in saida:
            saida.append(absoluta)
        if len(saida) >= MAX_PAGINAS_DOCUMENTOS:
            break
    return saida


def linhas_brutas_documentos(html_pagina: str) -> list[dict]:
    """O que a página TEM na seção de documentos, sem interpretar — para o probe.

    É o que se olha quando o parser e a página discordam: cada `<tr>` com as
    células em texto, os hrefs, as ações nos scripts e os ids numéricos.
    """
    marca = _MARCA_DOCUMENTOS.search(html_pagina)
    if not marca:
        return []
    saida = []
    for linha in _LINHA.findall(html_pagina[marca.end() :]):
        celulas = [c for c in (_texto_da_celula(x) for x in _CELULA.findall(linha)) if c]
        if not celulas:
            continue
        saida.append(
            {
                "celulas": celulas,
                "hrefs": [html_.unescape(h) for h in _HREF.findall(linha)],
                "acoes_js": _ACAO_JS.findall(html_.unescape(linha)),
                "ids": [m.group(1) for m in _HIDDEN_ID.finditer(linha)]
                + [m.group(1) for m in _ID_NUMERICO.finditer(html_.unescape(linha))],
            }
        )
    return saida


# ── Baixar o arquivo ───────────────────────────────────────────────────────
# O href da lista NÃO é um link público: é uma ação `.do` do webapp, servida
# só dentro da sessão. Aberto no navegador do gestor (que não tem sessão
# nenhuma), o Struts manda para o SSO e ele aterrissa em
# `idp.transferegov.sistema.gov.br/idp/` — tela de login, nunca o documento.
#
# Então o Hub faz a PONTE, como no PDF do DOU (§56c): refaz o rito do guest,
# baixa pela MESMA sessão e devolve os bytes. Nada é persistido — o arquivo é
# público na origem e cachear binário de terceiro cria acervo que ninguém
# pediu para manter (§56).

#: teto do arquivo trazido pela ponte — projeto básico com planta e memorial
#: passa de 40 MB (era o teto, e recusava documento legítimo com "grande
#: demais"). Acima de 100 MB é a fonte devolvendo outra coisa. A ponte carrega o
#: corpo em memória, com no máximo `_PONTES` simultâneas (§56e).
MAX_DOCUMENTO_BYTES = 100 * 1024 * 1024
#: o download tem timeout PRÓPRIO: o rito de sessão cabe em 60 s, mas um
#: projeto de 80 MB saindo de servidor de governo não — e estourar aqui era
#: "não foi possível baixar" sem a fonte ter negado nada.
TIMEOUT_DOWNLOAD_MS = 180_000

#: domínio da fonte. A URL vem de HTML raspado, então ela é ENTRADA externa:
#: sem esta trava, uma página adulterada faria a API buscar qualquer host da
#: rede interna e devolver o corpo ao usuário autenticado (SSRF).
HOST_FONTE = "transferegov.sistema.gov.br"

_RE_FILENAME = re.compile(r"""filename\*?=(?:UTF-8''|["']?)([^"';]+)""", re.I)


class DocumentoIndisponivel(RuntimeError):
    """A fonte não entregou o arquivo. Nunca é "o documento não existe"."""


def e_url_da_fonte(url: str | None) -> bool:
    """A URL é do webapp do Transferegov?"""
    try:
        partes = urlparse(str(url or ""))
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    return partes.scheme in ("http", "https") and (
        host == HOST_FONTE or host.endswith(f".{HOST_FONTE}")
    )


def nome_do_cabecalho(content_disposition: str | None) -> str | None:
    """O nome do arquivo que a fonte declarou, quando declarou."""
    if not content_disposition:
        return None
    m = _RE_FILENAME.search(content_disposition)
    if not m:
        return None
    nome = unquote(m.group(1).strip().strip("\"'")).strip()
    return nome.replace("/", "_").replace("\\", "_") or None


def e_pagina_de_login(url_final: str, content_type: str | None, conteudo: bytes) -> bool:
    """A resposta é o arquivo, ou é o SSO disfarçado de 200?

    O Struts responde 200 com a página do IdP (ou com o auto-post SAML) quando
    a sessão caiu. Entregar isso ao gestor com o nome do documento seria pior
    que falhar: ele anexaria ao processo um HTML de login.
    """
    try:
        host = (urlparse(url_final or "").hostname or "").lower()
    except ValueError:
        host = ""
    if host.startswith("idp.") or "/idp/" in (url_final or ""):
        return True
    if content_type and "text/html" in content_type.lower():
        return True
    inicio = conteudo[:1024].lstrip().lower()
    return inicio.startswith(b"<!doctype html") or inicio.startswith(b"<html")


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
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
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
                    parecer = _parse_parecer(await pg.inner_text("body"), texto, id_proposta, idp)
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
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
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
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
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
                return await self._documentos_completos(pg, await pg.content())
            finally:
                await browser.close()

    async def _documentos_completos(self, pg, pagina: str) -> list[dict]:
        """A lista INTEIRA: a página aberta mais as outras páginas do paginador.

        Best-effort por página: a que não abrir é registrada e pulada — perder
        uma página não pode custar as demais. Deduplica por (nome, url), porque
        o paginador costuma repetir a página corrente.
        """
        docs = parse_documentos(pagina)
        vistos = {(d["nome"], d.get("url")) for d in docs}
        visitadas: set[str] = set()
        fila = links_de_paginacao(pagina)
        while fila and len(visitadas) < MAX_PAGINAS_DOCUMENTOS:
            url = fila.pop(0)
            if url in visitadas:
                continue
            visitadas.add(url)
            try:
                await pg.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
                outra = await pg.content()
            except Exception as exc:  # noqa: BLE001 — uma página não derruba a lista
                log.warning("siconv documentos: página %s não abriu: %s", url, exc)
                continue
            for d in parse_documentos(outra):
                chave = (d["nome"], d.get("url"))
                if chave not in vistos:
                    vistos.add(chave)
                    docs.append(d)
            for extra in links_de_paginacao(outra):
                if extra not in visitadas and extra not in fila:
                    fila.append(extra)
        return docs[:MAX_DOCUMENTOS]

    async def _requisitar_arquivo(
        self, pg, url: str, referer: str
    ) -> tuple[bytes, str | None, str | None]:
        """Pede o arquivo pela sessão da página: GET e, se a ação recusar, POST.

        Ação Struts de download costuma aceitar os parâmetros pela query, mas
        há as que só leem o FORM (o botão da página submete um formulário, não
        segue um link) — para essas o GET devolve a própria página de novo, em
        HTML, e a ponte lia isso como "tela de login". O POST com os mesmos
        parâmetros é a segunda tentativa. O `Referer` entra porque é o que a
        página mandaria; sem ele há filtro que devolve a listagem.
        """
        motivos: list[str] = []
        cabecalhos = {"Referer": referer}
        tentativas = [
            ("GET", lambda: pg.request.get(url, timeout=TIMEOUT_DOWNLOAD_MS, headers=cabecalhos))
        ]
        partes = urlparse(url)
        if partes.query:
            form = dict(parse_qsl(partes.query, keep_blank_values=True))
            sem_query = urlunparse(partes._replace(query=""))
            tentativas.append(
                (
                    "POST",
                    lambda: pg.request.post(
                        sem_query, form=form, timeout=TIMEOUT_DOWNLOAD_MS, headers=cabecalhos
                    ),
                )
            )
        for metodo, pedir in tentativas:
            resposta = await pedir()
            if resposta.status >= 400:
                motivos.append(f"{metodo}: o portal do Transferegov respondeu {resposta.status}")
                continue
            conteudo = await resposta.body()
            headers = {k.lower(): v for k, v in (resposta.headers or {}).items()}
            content_type = headers.get("content-type")
            if e_pagina_de_login(resposta.url, content_type, conteudo):
                motivos.append(
                    f"{metodo}: o portal devolveu uma página HTML (login ou listagem) "
                    "em vez do arquivo"
                )
                continue
            if not conteudo:
                motivos.append(f"{metodo}: o portal devolveu um arquivo vazio")
                continue
            if len(conteudo) > MAX_DOCUMENTO_BYTES:
                raise DocumentoIndisponivel(
                    "o arquivo é grande demais para a ponte — baixe pelo portal"
                )
            return conteudo, content_type, nome_do_cabecalho(headers.get("content-disposition"))
        raise DocumentoIndisponivel(
            " · ".join(motivos) + " — o acesso livre do Transferegov pode estar indisponível"
        )

    async def baixar_documento(
        self, id_proposta: str, url: str
    ) -> tuple[bytes, str | None, str | None]:
        """Os BYTES de um documento digitalizado, pela sessão do acesso livre.

        Devolve `(conteúdo, content_type, nome declarado pela fonte)`.

        O rito é o mesmo dos pareceres, e o detalhe da proposta continua sendo
        obrigatório: o webapp guarda "a proposta corrente" na sessão, e a ação
        de download só serve o arquivo da proposta que ela conhece. Pular o
        detalhe devolve o login, que é exatamente o defeito que esta ponte
        existe para corrigir.

        A busca sai de `page.request`, que compartilha os cookies do contexto —
        `httpx` não serve aqui: a sessão vive no browser (o SSO depende de JS,
        e reproduzi-lo na mão termina em 401).
        """
        id_proposta = str(id_proposta).strip()
        if not id_proposta.isdigit():
            raise ValueError(
                f"idProposta do SIconv deve ser o id numérico interno (veio {id_proposta!r})"
            )
        if not e_url_da_fonte(url):
            raise DocumentoIndisponivel("o endereço do arquivo não é do portal do Transferegov")
        from playwright.async_api import async_playwright

        detalhe = f"{DETALHE}?idProposta={id_proposta}&destino=&idConvenio="
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                pg = await (await browser.new_context(locale="pt-BR")).new_page()
                await pg.goto(ENTRADA, wait_until="networkidle", timeout=TIMEOUT_MS)
                await pg.goto(detalhe, wait_until="networkidle", timeout=TIMEOUT_MS)
                if "Login" in (await pg.title()):
                    raise DocumentoIndisponivel(
                        "o acesso livre do Transferegov não abriu a proposta "
                        "(caiu na tela de login) — o rito do guest pode ter mudado"
                    )
                return await self._requisitar_arquivo(pg, url, detalhe)
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
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
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
                        # o HTML serve aos dois: a publicação precisa do
                        # rótulo da célula (não do texto corrido) e a lista de
                        # documentos está NESTA mesma página — de graça
                        pagina = await pg.content()
                        item["execucao"] = _parse_execucao(await pg.inner_text("body"), pagina)
                        item["documentos"] = await self._documentos_completos(pg, pagina)
                        await pg.goto(ABA_PARECERES, wait_until="networkidle", timeout=TIMEOUT_MS)
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
                            item["repasses"] = _parse_repasses(await pg.inner_text("body"))
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
                browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
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
