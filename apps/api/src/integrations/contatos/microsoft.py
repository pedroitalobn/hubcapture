"""Outlook / Microsoft 365 (Graph) — sync incremental por deltaLink.

O cursor do Graph é a própria URL do `deltaLink`; guardamos ela inteira em
`integracoes_contatos.sync_token` e, no próximo sync, chamamos direto.
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

GRAPH = "https://graph.microsoft.com/v1.0"
CONTATOS = f"{GRAPH}/me/contacts"
DELTA = f"{GRAPH}/me/contacts/delta"
EU = f"{GRAPH}/me"
PAGINA = 100


async def _token(cred: Credencial) -> str:
    if not cred.dados.get("access_token") or oauth.expirado(cred.dados):
        novos = await oauth.renovar(oauth.MICROSOFT, cred.dados)
        cred.atualizar(**novos)
    return cred.dados["access_token"]


async def _headers(cred: Credencial) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {await _token(cred)}",
        "Prefer": f"odata.maxpagesize={PAGINA}",
    }


def para_canonico(contato: dict) -> ContatoCanonico:
    telefones = [
        ContatoTelefone(tipo="trabalho", valor=v) for v in contato.get("businessPhones") or [] if v
    ]
    if contato.get("mobilePhone"):
        telefones.insert(0, ContatoTelefone(tipo="celular", valor=contato["mobilePhone"]))
    telefones += [
        ContatoTelefone(tipo="casa", valor=v) for v in contato.get("homePhones") or [] if v
    ]

    enderecos: list[ContatoEndereco] = []
    for tipo, chave in (("trabalho", "businessAddress"), ("pessoal", "homeAddress")):
        end = contato.get(chave) or {}
        if any(end.get(k) for k in ("street", "city", "state", "postalCode")):
            enderecos.append(
                ContatoEndereco(
                    tipo=tipo,
                    logradouro=end.get("street"),
                    cidade=end.get("city"),
                    uf=end.get("state"),
                    cep=end.get("postalCode"),
                )
            )

    return ContatoCanonico(
        nome=contato.get("givenName") or contato.get("displayName") or "Sem nome",
        sobrenome=contato.get("surname"),
        organizacao=contato.get("companyName"),
        cargo=contato.get("jobTitle"),
        emails=[
            ContatoEmail(tipo="trabalho", valor=e["address"])
            for e in contato.get("emailAddresses") or []
            if e.get("address")
        ],
        telefones=telefones,
        enderecos=enderecos,
        notas=contato.get("personalNotes"),
        tags=list(contato.get("categories") or []),
        origem="microsoft",
    )


def para_payload(canonico: ContatoCanonico) -> dict:
    comerciais = [t.valor for t in canonico.telefones if (t.tipo or "") != "celular"]
    celular = next((t.valor for t in canonico.telefones if (t.tipo or "") == "celular"), None)
    payload: dict = {
        "givenName": canonico.nome,
        "surname": canonico.sobrenome or "",
        "displayName": canonico.nome_completo,
        "companyName": canonico.organizacao or "",
        "jobTitle": canonico.cargo or "",
        "emailAddresses": [
            {"name": canonico.nome_completo, "address": e.valor} for e in canonico.emails
        ],
        # o Graph aceita no máximo 2 telefones comerciais
        "businessPhones": comerciais[:2],
        "personalNotes": canonico.notas or "",
        "categories": canonico.tags,
    }
    if celular:
        payload["mobilePhone"] = celular
    for tipo, chave in (("trabalho", "businessAddress"), ("pessoal", "homeAddress")):
        end = next((e for e in canonico.enderecos if (e.tipo or "") == tipo), None)
        if end:
            payload[chave] = {
                "street": end.logradouro or "",
                "city": end.cidade or "",
                "state": end.uf or "",
                "postalCode": end.cep or "",
            }
    return payload


def _externo(contato: dict) -> ContatoExterno:
    removido = "@removed" in contato
    return ContatoExterno(
        id_externo=contato.get("id", ""),
        canonico=None if removido else para_canonico(contato),
        etag=contato.get("@odata.etag"),
        removido=removido,
    )


class MicrosoftContatos:
    provedor_id = "microsoft"
    rotulo = "Outlook / Microsoft 365"
    tipo_auth = "oauth"

    async def disponivel(self) -> bool:
        return await oauth.configurado(oauth.MICROSOFT)

    async def identidade(self, cred: Credencial) -> str:
        dados = await request_json("GET", EU, headers=await _headers(cred))
        return dados.get("mail") or dados.get("userPrincipalName") or "conta microsoft"

    async def listar(self, cred: Credencial, sync_token: str | None) -> PaginaRemota:
        try:
            return await self._listar(cred, sync_token)
        except ProvedorClientError as exc:
            # deltaLink expirado/inválido → o Graph responde 410 (resync) ou 400
            if sync_token and exc.status in (400, 410):
                return await self._listar(cred, None)
            raise

    async def _listar(self, cred: Credencial, sync_token: str | None) -> PaginaRemota:
        headers = await _headers(cred)
        url: str | None = sync_token or DELTA
        itens: list[ContatoExterno] = []
        proximo: str | None = None
        while url:
            dados = await request_json("GET", url, headers=headers)
            itens.extend(_externo(c) for c in dados.get("value") or [])
            proximo = dados.get("@odata.deltaLink") or proximo
            url = dados.get("@odata.nextLink")
        return PaginaRemota(itens=itens, sync_token=proximo, completa=not sync_token)

    async def criar(self, cred: Credencial, canonico: ContatoCanonico) -> ContatoExterno:
        dados = await request_json(
            "POST", CONTATOS, headers=await _headers(cred), json=para_payload(canonico)
        )
        return _externo(dados)

    async def atualizar(
        self,
        cred: Credencial,
        id_externo: str,
        etag: str | None,
        canonico: ContatoCanonico,
    ) -> ContatoExterno:
        headers = await _headers(cred)
        if etag:
            headers["If-Match"] = etag
        dados = await request_json(
            "PATCH",
            f"{CONTATOS}/{id_externo}",
            headers=headers,
            json=para_payload(canonico),
        )
        return _externo(dados) if dados else ContatoExterno(id_externo=id_externo, etag=etag)

    async def remover(self, cred: Credencial, id_externo: str, etag: str | None) -> None:
        headers = await _headers(cred)
        if etag:
            headers["If-Match"] = etag
        await request_json("DELETE", f"{CONTATOS}/{id_externo}", headers=headers)


microsoft_contatos = register(MicrosoftContatos())
