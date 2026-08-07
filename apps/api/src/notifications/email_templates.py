"""Templates de e-mail transacional (texto + HTML simples e responsivo).

Cada função devolve `(assunto, corpo_txt, corpo_html)`. HTML minimalista com
largura máxima e cores neutras — renderiza bem em clientes de e-mail.
"""

from __future__ import annotations

_WRAP = (
    '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
    'max-width:480px;margin:0 auto;padding:24px;color:#111">'
    '<h1 style="font-size:20px;margin:0 0 8px">Hub Capture</h1>{body}'
    '<p style="font-size:12px;color:#888;margin-top:24px">'
    "Se você não solicitou este e-mail, ignore-o.</p></div>"
)


def _botao(url: str, label: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;background:#111;color:#fff;'
        "text-decoration:none;padding:10px 16px;border-radius:8px;"
        f'margin:12px 0">{label}</a>'
    )


def boas_vindas(nome: str | None) -> tuple[str, str, str]:
    ola = f"Olá, {nome}!" if nome else "Bem-vindo(a)!"
    txt = (
        f"{ola}\n\nSua conta no Hub Capture foi criada. "
        "Acompanhe captação, repasses, conformidade e obras do seu território "
        "num só painel."
    )
    html = _WRAP.format(
        body=f"<p>{ola}</p><p>Sua conta foi criada. Acompanhe captação, repasses, "
        "conformidade e obras do seu território num só painel.</p>"
    )
    return "Bem-vindo(a) ao Hub Capture", txt, html


def redefinir_senha(url: str) -> tuple[str, str, str]:
    txt = (
        "Recebemos um pedido para redefinir sua senha.\n\n"
        f"Abra o link para criar uma nova senha:\n{url}\n\n"
        "O link expira em 1 hora."
    )
    html = _WRAP.format(
        body="<p>Recebemos um pedido para redefinir sua senha.</p>"
        + _botao(url, "Redefinir senha")
        + '<p style="font-size:12px;color:#888">O link expira em 1 hora.</p>'
    )
    return "Redefinir sua senha — Hub Capture", txt, html


def verificar_email(url: str) -> tuple[str, str, str]:
    txt = f"Confirme seu e-mail para ativar a conta:\n{url}"
    html = _WRAP.format(
        body="<p>Confirme seu e-mail para ativar a conta.</p>" + _botao(url, "Confirmar e-mail")
    )
    return "Confirme seu e-mail — Hub Capture", txt, html


def convite(url: str, papel: str | None) -> tuple[str, str, str]:
    papel_txt = f" como <b>{papel}</b>" if papel else ""
    txt = (
        f"Você foi convidado(a) para o Hub Capture{(' como ' + papel) if papel else ''}.\n\n"
        f"Aceite o convite e crie sua senha:\n{url}"
    )
    html = _WRAP.format(
        body=f"<p>Você foi convidado(a) para o Hub Capture{papel_txt}.</p>"
        + _botao(url, "Aceitar convite")
    )
    return "Seu convite para o Hub Capture", txt, html


def alertas_resumo(linhas: list[str], url_painel: str | None) -> tuple[str, str, str]:
    """Resumo dos alertas novos (nova proposta / oportunidade / mudança)."""
    corpo = "\n".join(f"• {li}" for li in linhas)
    txt = "Novidades no seu território:\n\n" f"{corpo}\n\n" + (
        f"Veja no painel: {url_painel}" if url_painel else "Veja no painel do Hub Capture."
    )
    itens_html = "".join(f'<li style="margin:4px 0">{li}</li>' for li in linhas)
    botao = _botao(url_painel, "Abrir o painel") if url_painel else ""
    html = _WRAP.format(body=f"<p>Novidades no seu território:</p><ul>{itens_html}</ul>{botao}")
    return "Hub Capture — novidades no seu território", txt, html
