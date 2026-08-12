"""Google Contacts (People API) — sync incremental por syncToken.

Rotas/campos isolados em constantes (ponto de calibração, como nos connectors).
Escopo `.../auth/contacts` (leitura e escrita dos contatos do usuário).
"""

from __future__ import annotations

from ...schemas.contato import (
    ContatoCanonico,
    ContatoEmail,
    ContatoEndereco,
    ContatoTelefone,
)
from . import oauth
from ._http import ProvedorClientError, request_json
from .base import ContatoExterno, Credencial, PaginaRemota, register

API = "https://people.googleapis.com/v1"
CONEXOES = f"{API}/people/me/connections"
CRIAR = f"{API}/people:createContact"
EU = f"{API}/people/me"

CAMPOS = "names,emailAddresses,phoneNumbers,organizations,addresses,biographies,metadata"
CAMPOS_ESCRITA = "names,emailAddresses,phoneNumbers,organizations,addresses,biographies"
PAGINA = 200

_TIPO_EMAIL = {"work": "trabalho", "home": "pessoal"}
_TIPO_TEL = {"mobile": "celular", "work": "trabalho", "home": "casa"}
_TIPO_EMAIL_SAIDA = {"trabalho": "work", "pessoal": "home"}
_TIPO_TEL_SAIDA = {"celular": "mobile", "trabalho": "work", "casa": "home"}


async def _token(cred: Credencial) -> str:
    """Access token válido — renova (e marca a credencial) quando expirado."""
    if not cred.dados.get("access_token") or oauth.expirado(cred.dados):
        novos = await oauth.renovar(oauth.GOOGLE, cred.dados)
        cred.atualizar(**novos)
    return cred.dados["access_token"]


async def _headers(cred: Credencial) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(cred)}"}


def para_canonico(person: dict) -> ContatoCanonico:
    nomes = (person.get("names") or [{}])[0]
    orgs = (person.get("organizations") or [{}])[0]
    bios = person.get("biographies") or []
    return ContatoCanonico(
        nome=nomes.get("givenName") or nomes.get("displayName") or "Sem nome",
        sobrenome=nomes.get("familyName"),
        organizacao=orgs.get("name"),
        cargo=orgs.get("title"),
        emails=[
            ContatoEmail(tipo=_TIPO_EMAIL.get((e.get("type") or "").lower()), valor=e["value"])
            for e in person.get("emailAddresses") or []
            if e.get("value")
        ],
        telefones=[
            ContatoTelefone(tipo=_TIPO_TEL.get((t.get("type") or "").lower()), valor=t["value"])
            for t in person.get("phoneNumbers") or []
            if t.get("value")
        ],
        enderecos=[
            ContatoEndereco(
                tipo=_TIPO_EMAIL.get((a.get("type") or "").lower()),
                logradouro=a.get("streetAddress"),
                cidade=a.get("city"),
                uf=a.get("region"),
                cep=a.get("postalCode"),
            )
            for a in person.get("addresses") or []
        ],
        notas=(bios[0].get("value") if bios else None),
        origem="google",
    )


def para_payload(canonico: ContatoCanonico) -> dict:
    payload: dict = {
        "names": [{"givenName": canonico.nome, "familyName": canonico.sobrenome or ""}],
        "emailAddresses": [
            {"value": e.valor, "type": _TIPO_EMAIL_SAIDA.get((e.tipo or "").lower(), "other")}
            for e in canonico.emails
        ],
        "phoneNumbers": [
            {"value": t.valor, "type": _TIPO_TEL_SAIDA.get((t.tipo or "").lower(), "other")}
            for t in canonico.telefones
        ],
        "addresses": [
            {
                "streetAddress": a.logradouro or "",
                "city": a.cidade or "",
                "region": a.uf or "",
                "postalCode": a.cep or "",
                "type": "work" if (a.tipo or "") == "trabalho" else "home",
            }
            for a in canonico.enderecos
        ],
    }
    if canonico.organizacao or canonico.cargo:
        payload["organizations"] = [
            {"name": canonico.organizacao or "", "title": canonico.cargo or ""}
        ]
    if canonico.notas:
        payload["biographies"] = [{"value": canonico.notas, "contentType": "TEXT_PLAIN"}]
    return payload


def _externo(person: dict) -> ContatoExterno:
    metadata = person.get("metadata") or {}
    removido = bool(metadata.get("deleted"))
    return ContatoExterno(
        id_externo=person.get("resourceName", ""),
        canonico=None if removido else para_canonico(person),
        etag=person.get("etag"),
        removido=removido,
    )


class GoogleContatos:
    provedor_id = "google"
    rotulo = "Google Contacts"
    tipo_auth = "oauth"

    async def disponivel(self) -> bool:
        return await oauth.configurado(oauth.GOOGLE)

    async def identidade(self, cred: Credencial) -> str:
        dados = await request_json(
            "GET", EU, headers=await _headers(cred), params={"personFields": "emailAddresses"}
        )
        emails = dados.get("emailAddresses") or [{}]
        return emails[0].get("value") or "conta google"

    async def listar(self, cred: Credencial, sync_token: str | None) -> PaginaRemota:
        try:
            return await self._listar(cred, sync_token)
        except ProvedorClientError as exc:
            # syncToken vencido (>7 dias sem sync) → o Google manda refazer full
            if sync_token and exc.status == 400:
                return await self._listar(cred, None)
            raise

    async def _listar(self, cred: Credencial, sync_token: str | None) -> PaginaRemota:
        headers = await _headers(cred)
        itens: list[ContatoExterno] = []
        page_token: str | None = None
        proximo: str | None = None
        while True:
            params = {
                "personFields": CAMPOS,
                "pageSize": str(PAGINA),
                "requestSyncToken": "true",
            }
            if sync_token:
                params["syncToken"] = sync_token
            if page_token:
                params["pageToken"] = page_token
            dados = await request_json("GET", CONEXOES, headers=headers, params=params)
            itens.extend(_externo(p) for p in dados.get("connections") or [])
            proximo = dados.get("nextSyncToken") or proximo
            page_token = dados.get("nextPageToken")
            if not page_token:
                break
        return PaginaRemota(itens=itens, sync_token=proximo, completa=not sync_token)

    async def criar(self, cred: Credencial, canonico: ContatoCanonico) -> ContatoExterno:
        dados = await request_json(
            "POST",
            CRIAR,
            headers=await _headers(cred),
            params={"personFields": CAMPOS},
            json=para_payload(canonico),
        )
        return _externo(dados)

    async def atualizar(
        self,
        cred: Credencial,
        id_externo: str,
        etag: str | None,
        canonico: ContatoCanonico,
    ) -> ContatoExterno:
        corpo = para_payload(canonico)
        if etag:
            corpo["etag"] = etag  # o People API recusa update sem etag corrente
        dados = await request_json(
            "PATCH",
            f"{API}/{id_externo}:updateContact",
            headers=await _headers(cred),
            params={"updatePersonFields": CAMPOS_ESCRITA, "personFields": CAMPOS},
            json=corpo,
        )
        return _externo(dados)

    async def remover(self, cred: Credencial, id_externo: str, etag: str | None) -> None:
        await request_json(
            "DELETE", f"{API}/{id_externo}:deleteContact", headers=await _headers(cred)
        )


google_contatos = register(GoogleContatos())
