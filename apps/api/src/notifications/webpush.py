"""Web Push (notificação no navegador/celular) — RFC 8291 + RFC 8292 (§63).

Sem dependência nova: a cifra do payload (aes128gcm) e a assinatura VAPID
(ES256) saem da `cryptography`, que o projeto já usa para o Fernet, e o POST
vai por `httpx`. O pywebpush faria o mesmo com três pacotes a mais.

O par VAPID é GERADO no primeiro uso e gravado no painel admin
(`webpush_vapid_*`, privada cifrada em repouso): push funciona sem ninguém
precisar rodar `openssl` nem mexer no `.env`. Trocar o par invalida as
inscrições existentes — o navegador inscreveu com a chave pública antiga.

Como o resto dos canais, é provider-OPCIONAL e best-effort: falha de envio
nunca derruba a varredura de alertas (o alerta continua no painel).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..db.session import SessionLocal
from ..services import config as config_service

log = logging.getLogger("hubcapture.webpush")

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
#: por quanto tempo o serviço de push guarda a mensagem se o aparelho estiver
#: desligado — um alerta de prazo que chega dois dias depois já não serve
TTL_SEGUNDOS = 24 * 3600
CONTATO_PADRAO = "mailto:suporte@hubcapture.com.br"
_RS = 4096  # record size do aes128gcm (a mensagem cabe num registro só)


def b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def b64url_decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# ------------------------------------------------------------------ chaves


@dataclass(frozen=True)
class ChavesVapid:
    publica: str  # ponto não-comprimido (65 bytes), base64url — vai ao navegador
    privada: str  # escalar d (32 bytes), base64url


def gerar_chaves() -> ChavesVapid:
    chave = ec.generate_private_key(ec.SECP256R1())
    d = chave.private_numbers().private_value.to_bytes(32, "big")
    pub = chave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return ChavesVapid(publica=b64url(pub), privada=b64url(d))


def _privada(chaves: ChavesVapid) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(
        int.from_bytes(b64url_decode(chaves.privada), "big"), ec.SECP256R1()
    )


_LOCK_CHAVES = asyncio.Lock()


async def _ler_chaves() -> ChavesVapid | None:
    pub = await config_service.resolver("webpush_vapid_public_key")
    priv = await config_service.resolver("webpush_vapid_private_key")
    return ChavesVapid(publica=pub, privada=priv) if pub and priv else None


async def garantir_chaves() -> ChavesVapid:
    """O par VAPID do painel — gerado e gravado na primeira chamada.

    Sob lock: duas inscrições simultâneas no primeiro uso gerariam DOIS pares,
    e o segundo gravado invalidaria a inscrição feita com o primeiro.
    """
    atuais = await _ler_chaves()
    if atuais:
        return atuais
    async with _LOCK_CHAVES:
        atuais = await _ler_chaves()
        if atuais:
            return atuais
        novas = gerar_chaves()
        async with SessionLocal() as s:
            await config_service.definir(s, "webpush_vapid_public_key", novas.publica)
            await config_service.definir(s, "webpush_vapid_private_key", novas.privada)
            await s.commit()
        log.info("web push: par VAPID gerado e gravado no painel admin")
        return novas


# ------------------------------------------------------------------ VAPID


def cabecalho_vapid(
    endpoint: str, chaves: ChavesVapid, contato: str, agora: int | None = None
) -> str:
    """`Authorization: vapid t=<JWT ES256>, k=<chave pública>` (RFC 8292)."""
    partes = urlsplit(endpoint)
    claims = {
        "aud": f"{partes.scheme}://{partes.netloc}",
        "exp": int(agora or time.time()) + 12 * 3600,
        "sub": contato,
    }
    cabecalho = {"typ": "JWT", "alg": "ES256"}
    assinado = ".".join(
        b64url(json.dumps(x, separators=(",", ":")).encode()) for x in (cabecalho, claims)
    )
    der = _privada(chaves).sign(assinado.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    jwt = f"{assinado}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={chaves.publica}"


# ------------------------------------------------------------------ cifra


def _hkdf(salt: bytes, ikm: bytes, info: bytes, tamanho: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:tamanho]


def cifrar(
    payload: bytes,
    p256dh: str,
    auth: str,
    *,
    efemera: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """Corpo `aes128gcm` para ESTE navegador (RFC 8291 §3–4)."""
    ua_pub_bytes = b64url_decode(p256dh)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    efemera = efemera or ec.generate_private_key(ec.SECP256R1())
    as_pub = efemera.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    segredo = efemera.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf(b64url_decode(auth), segredo, b"WebPush: info\x00" + ua_pub_bytes + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    cifrado = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # 0x02 = último registro
    return salt + _RS.to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + cifrado


# ------------------------------------------------------------------ envio


#: Serviços de push dos navegadores (Chrome/Edge/Android, Firefox, Safari/iOS,
#: Windows). O endpoint vem do CLIENTE e vira destino de POST do servidor —
#: sem esta lista, qualquer usuário faria a API bater num host interno.
HOSTS_PUSH = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    ".push.services.mozilla.com",
    "push.services.mozilla.com",
    ".push.apple.com",
    ".notify.windows.com",
)


def endpoint_permitido(endpoint: str) -> bool:
    partes = urlsplit(endpoint)
    if partes.scheme != "https" or not partes.hostname:
        return False
    host = partes.hostname.lower()
    return any(host == h or (h.startswith(".") and host.endswith(h)) for h in HOSTS_PUSH)


class InscricaoExpirada(Exception):
    """O serviço de push respondeu 404/410 — a inscrição não existe mais."""


async def enviar(endpoint: str, p256dh: str, auth: str, mensagem: dict) -> bool:
    """Entrega UMA notificação a UM navegador. `InscricaoExpirada` = apagar."""
    if not endpoint_permitido(endpoint):  # inscrição gravada antes da trava
        raise InscricaoExpirada("endpoint fora dos serviços de push")
    chaves = await garantir_chaves()
    contato = await config_service.resolver("webpush_contato") or CONTATO_PADRAO
    corpo = cifrar(json.dumps(mensagem, ensure_ascii=False).encode(), p256dh, auth)
    headers = {
        "Authorization": cabecalho_vapid(endpoint, chaves, contato),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SEGUNDOS),
        "Urgency": "normal",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(endpoint, content=corpo, headers=headers)
    if resp.status_code in (404, 410):
        raise InscricaoExpirada(f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise RuntimeError(f"push recusado: HTTP {resp.status_code} {resp.text[:200]}")
    return True
