"""CardDAV — Apple/iCloud (`apple`) e servidores genéricos (`carddav`).

Apple não publica API REST de contatos: o caminho oficial é CardDAV com **senha
de app** (appleid.apple.com → Segurança → Senhas de app). A mesma implementação
serve Nextcloud/SOGo/Radicale via `carddav` com a URL do servidor.

Cursor incremental: o CTag da coleção (`getctag`). CTag igual = nada mudou desde
o último sync → não baixa nada. CTag diferente = listagem cheia (o protocolo não
dá delta por item sem `sync-collection`, que nem todo servidor implementa).
"""

from __future__ import annotations

import uuid as _uuid
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from ...schemas.contato import ContatoCanonico
from ...services import config as config_service
from . import vcard
from ._http import ProvedorClientError, request
from .base import ContatoExterno, Credencial, PaginaRemota, ProvedorIndisponivel, register

DAV = "DAV:"
CARDDAV = "urn:ietf:params:xml:ns:carddav"
CALSERVER = "http://calendarserver.org/ns/"
NS = {"d": DAV, "c": CARDDAV, "cs": CALSERVER}

XML_PRINCIPAL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
)
XML_HOME = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><c:addressbook-home-set/></d:prop></d:propfind>"
)
XML_COLECOES = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">'
    "<d:prop><d:resourcetype/><d:displayname/><cs:getctag/></d:prop></d:propfind>"
)
XML_ETAGS = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">'
    "<d:prop><d:getetag/><d:resourcetype/><cs:getctag/></d:prop></d:propfind>"
)
LOTE_MULTIGET = 50


def _texto(el: ET.Element | None) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def _origem(url: str) -> str:
    partes = urlparse(url)
    return f"{partes.scheme}://{partes.netloc}"


def _absoluta(base: str, href: str) -> str:
    return href if href.startswith("http") else urljoin(_origem(base), href)


class CardDAVContatos:
    """Provedor CardDAV. `apple` e `carddav` são a mesma implementação com
    base URL/rótulo diferentes."""

    def __init__(self, provedor_id: str, rotulo: str, chave_url: str | None) -> None:
        self.provedor_id = provedor_id
        self.rotulo = rotulo
        self.tipo_auth = "senha_app"
        self._chave_url = chave_url

    async def disponivel(self) -> bool:
        # não depende de credencial de aplicação: basta a conta + senha de app
        return True

    async def base_url(self, cred: Credencial) -> str:
        url = cred.dados.get("base_url")
        if not url and self._chave_url:
            url = await config_service.resolver(self._chave_url)
        if not url:
            raise ProvedorIndisponivel(f"{self.provedor_id}: URL do servidor não definida")
        return url.rstrip("/") + "/"

    def _auth(self, cred: Credencial) -> tuple[str, str]:
        senha = cred.dados.get("senha_app")
        if not senha:
            raise ProvedorIndisponivel(f"{self.provedor_id}: senha de app ausente")
        return (cred.conta, senha)

    async def _dav(
        self,
        cred: Credencial,
        method: str,
        url: str,
        *,
        body: str | None = None,
        depth: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        """Requisição DAV seguindo redirect na mão (para não perder o Basic)."""
        cabecalhos = {"Content-Type": 'application/xml; charset="utf-8"', **(headers or {})}
        if depth is not None:
            cabecalhos["Depth"] = depth
        alvo = url
        for _ in range(4):
            resp = await request(
                method,
                alvo,
                headers=cabecalhos,
                content=body,
                auth=self._auth(cred),
                follow_redirects=False,
            )
            if resp.status_code in (301, 302, 307, 308) and resp.headers.get("location"):
                alvo = _absoluta(alvo, resp.headers["location"])
                continue
            return resp
        raise ProvedorClientError(f"{self.provedor_id}: redirecionamento em loop", 508)

    # ── descoberta ────────────────────────────────────────────────────────
    async def _colecao(self, cred: Credencial) -> tuple[str, str | None]:
        """URL da agenda + CTag. Descobre uma vez e guarda na credencial."""
        base = await self.base_url(cred)
        salva = cred.dados.get("colecao_url")
        if salva:
            return salva, await self._ctag(cred, salva)

        resp = await self._dav(cred, "PROPFIND", base, body=XML_PRINCIPAL, depth="0")
        principal = _texto(
            ET.fromstring(resp.text).find(".//d:current-user-principal/d:href", NS)
        )
        if not principal:
            raise ProvedorClientError(f"{self.provedor_id}: principal não encontrado", 404)

        resp = await self._dav(
            cred, "PROPFIND", _absoluta(base, principal), body=XML_HOME, depth="0"
        )
        home = _texto(ET.fromstring(resp.text).find(".//c:addressbook-home-set/d:href", NS))
        if not home:
            raise ProvedorClientError(f"{self.provedor_id}: address book home ausente", 404)

        resp = await self._dav(
            cred, "PROPFIND", _absoluta(base, home), body=XML_COLECOES, depth="1"
        )
        raiz = ET.fromstring(resp.text)
        for resposta in raiz.findall("d:response", NS):
            if resposta.find(".//d:resourcetype/c:addressbook", NS) is None:
                continue
            href = _texto(resposta.find("d:href", NS))
            if not href:
                continue
            colecao = _absoluta(base, href)
            cred.atualizar(colecao_url=colecao)
            return colecao, _texto(resposta.find(".//cs:getctag", NS))
        raise ProvedorClientError(f"{self.provedor_id}: nenhuma agenda CardDAV", 404)

    async def _ctag(self, cred: Credencial, colecao: str) -> str | None:
        resp = await self._dav(cred, "PROPFIND", colecao, body=XML_COLECOES, depth="0")
        return _texto(ET.fromstring(resp.text).find(".//cs:getctag", NS))

    async def identidade(self, cred: Credencial) -> str:
        await self._colecao(cred)  # valida credencial na conexão
        return cred.conta

    # ── leitura ───────────────────────────────────────────────────────────
    async def listar(self, cred: Credencial, sync_token: str | None) -> PaginaRemota:
        colecao, ctag = await self._colecao(cred)
        if sync_token and ctag and sync_token == ctag:
            return PaginaRemota(itens=[], sync_token=ctag, completa=False)

        resp = await self._dav(cred, "PROPFIND", colecao, body=XML_ETAGS, depth="1")
        raiz = ET.fromstring(resp.text)
        etags: dict[str, str | None] = {}
        for resposta in raiz.findall("d:response", NS):
            href = _texto(resposta.find("d:href", NS))
            if not href or href.rstrip("/") == urlparse(colecao).path.rstrip("/"):
                continue  # a própria coleção
            if resposta.find(".//d:resourcetype/d:collection", NS) is not None:
                continue
            if not href.lower().endswith(".vcf"):
                continue
            etags[href] = _texto(resposta.find(".//d:getetag", NS))

        itens: list[ContatoExterno] = []
        hrefs = list(etags)
        for i in range(0, len(hrefs), LOTE_MULTIGET):
            itens.extend(await self._multiget(cred, colecao, hrefs[i : i + LOTE_MULTIGET], etags))
        return PaginaRemota(itens=itens, sync_token=ctag, completa=True)

    async def _multiget(
        self,
        cred: Credencial,
        colecao: str,
        hrefs: list[str],
        etags: dict[str, str | None],
    ) -> list[ContatoExterno]:
        corpo = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<c:addressbook-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
            "<d:prop><d:getetag/><c:address-data/></d:prop>"
            + "".join(f"<d:href>{h}</d:href>" for h in hrefs)
            + "</c:addressbook-multiget>"
        )
        try:
            resp = await self._dav(cred, "REPORT", colecao, body=corpo, depth="1")
        except ProvedorClientError:
            # servidor sem REPORT/multiget → cai para GET individual
            return [await self._buscar(cred, colecao, h, etags.get(h)) for h in hrefs]

        itens: list[ContatoExterno] = []
        for resposta in ET.fromstring(resp.text).findall("d:response", NS):
            href = _texto(resposta.find("d:href", NS))
            dados = _texto(resposta.find(".//c:address-data", NS))
            if not href or not dados:
                continue
            cartoes = vcard.parsear(dados)
            if not cartoes:
                continue
            canonico = cartoes[0]
            canonico.origem = self.provedor_id
            itens.append(
                ContatoExterno(
                    id_externo=href,
                    canonico=canonico,
                    etag=_texto(resposta.find(".//d:getetag", NS)) or etags.get(href),
                )
            )
        return itens

    async def _buscar(
        self, cred: Credencial, colecao: str, href: str, etag: str | None
    ) -> ContatoExterno:
        resp = await self._dav(cred, "GET", _absoluta(colecao, href))
        cartoes = vcard.parsear(resp.text)
        canonico = cartoes[0] if cartoes else None
        if canonico:
            canonico.origem = self.provedor_id
        return ContatoExterno(
            id_externo=href, canonico=canonico, etag=resp.headers.get("etag") or etag
        )

    # ── escrita ───────────────────────────────────────────────────────────
    async def criar(self, cred: Credencial, canonico: ContatoCanonico) -> ContatoExterno:
        colecao, _ = await self._colecao(cred)
        nome_arquivo = f"{_uuid.uuid4()}.vcf"
        alvo = urljoin(colecao if colecao.endswith("/") else colecao + "/", nome_arquivo)
        resp = await self._dav(
            cred,
            "PUT",
            alvo,
            body=vcard.serializar(canonico, uid=nome_arquivo[:-4]),
            headers={"Content-Type": "text/vcard; charset=utf-8", "If-None-Match": "*"},
        )
        return ContatoExterno(
            id_externo=urlparse(alvo).path,
            canonico=canonico,
            etag=resp.headers.get("etag"),
        )

    async def atualizar(
        self,
        cred: Credencial,
        id_externo: str,
        etag: str | None,
        canonico: ContatoCanonico,
    ) -> ContatoExterno:
        colecao, _ = await self._colecao(cred)
        alvo = _absoluta(colecao, id_externo)
        headers = {"Content-Type": "text/vcard; charset=utf-8"}
        if etag:
            headers["If-Match"] = etag
        resp = await self._dav(
            cred,
            "PUT",
            alvo,
            body=vcard.serializar(canonico, uid=id_externo.rsplit("/", 1)[-1][:-4]),
            headers=headers,
        )
        return ContatoExterno(
            id_externo=id_externo, canonico=canonico, etag=resp.headers.get("etag")
        )

    async def remover(self, cred: Credencial, id_externo: str, etag: str | None) -> None:
        colecao, _ = await self._colecao(cred)
        headers = {"If-Match": etag} if etag else {}
        await self._dav(cred, "DELETE", _absoluta(colecao, id_externo), headers=headers)


apple_contatos = register(
    CardDAVContatos("apple", "Apple / iCloud (CardDAV)", "apple_carddav_url")
)
carddav_contatos = register(
    CardDAVContatos("carddav", "CardDAV (Nextcloud, SOGo, outros)", None)
)
