"""Envio de e-mail transacional — provider-opcional (SMTP), como o Uniq.

Credenciais vêm do painel admin (config runtime). Sem `email_smtp_host`+
`email_from` configurados o envio é **desabilitado** (retorna False, sem erro) —
o fluxo de negócio continua (o token de reset, por ex., ainda existe na API).

Usa `smtplib` da stdlib em thread (sem nova dependência). Suporta TLS (STARTTLS)
quando `email_smtp_port` = 587 e SSL quando 465.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from ..services import config as config_service


async def habilitado() -> bool:
    host = await config_service.resolver("email_smtp_host")
    remetente = await config_service.resolver("email_from")
    return bool(host and remetente)


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
    """Envia um e-mail. Retorna True se despachado, False se desabilitado."""
    host = await config_service.resolver("email_smtp_host")
    remetente = await config_service.resolver("email_from")
    if not host or not remetente:
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
