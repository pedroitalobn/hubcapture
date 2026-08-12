"""Envio de e-mail transacional — Maileroo (API HTTP) com fallback SMTP.

Ordem de preferência:
  1. Maileroo — se `MAILEROO_API_KEY` (env) ou `maileroo_api_key` (painel) setado.
  2. SMTP    — se `email_smtp_host` (painel admin) setado.
Sem nenhum dos dois + um remetente (`EMAIL_FROM` env ou `email_from` painel), o
envio fica DESABILITADO (retorna False, sem erro) — o fluxo de negócio segue
(o token de reset/convite ainda existe na API).

Remetente e chave aceitam ENV (settings) OU painel admin — o painel sobrescreve.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from ..core.config import settings
from ..services import config as config_service


async def _resolver(chave: str, fallback: str = "") -> str:
    """Valor do painel admin (runtime) OU do settings/env como fallback."""
    return (await config_service.resolver(chave)) or fallback


def _parse_remetente(remetente: str) -> tuple[str, str]:
    """'Nome <a@b>' -> ('a@b', 'Nome'); 'a@b' -> ('a@b', '')."""
    if "<" in remetente and ">" in remetente:
        nome = remetente.split("<", 1)[0].strip().strip('"')
        addr = remetente.split("<", 1)[1].split(">", 1)[0].strip()
        return addr, nome
    return remetente.strip(), ""


async def _enviar_maileroo(
    api_key: str,
    remetente: str,
    destinatario: str,
    assunto: str,
    corpo_txt: str,
    corpo_html: str | None,
) -> None:
    """POST na API v2 do Maileroo (X-API-Key). Levanta em status != 2xx."""
    addr, nome = _parse_remetente(remetente)
    url = await _resolver("maileroo_api_url", settings.maileroo_api_url)
    payload = {
        "from": {"address": addr, "display_name": nome or addr},
        "to": [{"address": destinatario}],
        "subject": assunto,
        "plain": corpo_txt,
    }
    if corpo_html:
        payload["html"] = corpo_html
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers={"X-API-Key": api_key})
        resp.raise_for_status()


async def habilitado() -> bool:
    remetente = await _resolver("email_from", settings.email_from)
    if not remetente:
        return False
    maileroo = await _resolver("maileroo_api_key", settings.maileroo_api_key)
    host = await config_service.resolver("email_smtp_host")
    return bool(maileroo or host)


def _enviar_sync(
    *,
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    remetente: str,
    destinatario: str,
    assunto: str,
    corpo_txt: str,
    corpo_html: str | None,
) -> None:
    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo_txt)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except smtplib.SMTPException:
                pass  # servidor sem STARTTLS (dev/local)
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)


async def enviar(
    destinatario: str,
    assunto: str,
    corpo_txt: str,
    corpo_html: str | None = None,
) -> bool:
    """Envia um e-mail. Retorna True se despachado, False se desabilitado.

    Preferência: Maileroo (API) > SMTP. Remetente/chave: painel admin > env.
    """
    remetente = await _resolver("email_from", settings.email_from)
    if not remetente:
        return False

    # 1) Maileroo (API HTTP) — caminho preferido
    maileroo = await _resolver("maileroo_api_key", settings.maileroo_api_key)
    if maileroo:
        await _enviar_maileroo(maileroo, remetente, destinatario, assunto, corpo_txt, corpo_html)
        return True

    # 2) SMTP (config do painel admin)
    host = await config_service.resolver("email_smtp_host")
    if not host:
        return False
    port = int(await config_service.resolver("email_smtp_port") or "587")
    user = await config_service.resolver("email_smtp_user")
    password = await config_service.resolver("email_smtp_password")

    await asyncio.to_thread(
        _enviar_sync,
        host=host,
        port=port,
        user=user,
        password=password,
        remetente=remetente,
        destinatario=destinatario,
        assunto=assunto,
        corpo_txt=corpo_txt,
        corpo_html=corpo_html,
    )
    return True
