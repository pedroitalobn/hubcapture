"""Templates de e-mail transacional (texto + HTML com a identidade do Hub).

Cada função devolve `(assunto, corpo_txt, corpo_html)`. O HTML segue o design
system Bancada — mesma disciplina do espelho em PDF (§34): banda da marca em
abyss com o brand-dot em gradiente lime→aqua, fio de gradiente e conteúdo nos
tokens do tema CLARO de `globals.css` (e-mail é documento externo, reencaminhado
e impresso — nunca segue o tema escuro do painel).

Restrições de cliente de e-mail: layout em <table>, todo estilo inline, cores
com fallback sólido antes do gradiente (Outlook ignora linear-gradient) e fonte
com stack de sistema — nada de webfont.
"""

from __future__ import annotations

from html import escape

from ..services import identidade

# Tokens da paleta (globals.css, tema claro) — espelho de services/pdf.py
_LIME = "#cef79e"  # acento primário da marca
_AQUA = "#8be0d4"  # acento secundário (gradientes)
_ABYSS = "#222f30"  # banda da marca / tinta / botão primário
_BONE = "#f7f7f5"  # canvas claro (--surface)
_PAPER = "#ffffff"  # card (--card)
_INK = "#222f30"  # --ink
_INK2 = "#46504f"  # --ink-2 (leitura)
_INK3 = "#7f8a80"  # --ink-3 (metadata)
_HAIRLINE = "#c9cbbe"  # --hairline (lichen)

# Sem aspas nos nomes compostos: os atributos style='…' usam aspas simples e
# uma aspa interna terminaria o atributo no meio (nome multi-palavra sem aspas
# é CSS válido — sequência de identificadores).
_SANS = "Inter Tight,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
_MONO = "Roboto Mono,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

_GRAD = f"linear-gradient(90deg,{_LIME},{_AQUA})"

# Documento completo: <meta color-scheme> segura o dark-mode agressivo de
# alguns clientes; o preheader é o trecho que aparece na lista da inbox.
_DOC = (
    "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<meta name='color-scheme' content='light'>"
    "<meta name='supported-color-schemes' content='light'></head>"
    f'<body style="margin:0;padding:0;background:{_BONE}">'
    "<div style='display:none;max-height:0;overflow:hidden;mso-hide:all'>"
    "{preheader}</div>"
    "{tabela}"
    "</body></html>"
)

def _cores() -> dict[str, str]:
    """Banda/acento da identidade em uso (§69). O Hub Capture mantém a arte
    original (gradiente lime→aqua); marca própria usa as cores sólidas dela —
    gradiente de duas cores inventadas a partir de uma só ficaria sem dono."""
    ident = identidade.atual()
    if ident.padrao:
        return {"banda": _ABYSS, "acento": _LIME, "grad": _GRAD}
    return {"banda": ident.escuro, "acento": ident.acento, "grad": ident.acento}


def _nome() -> str:
    return identidade.atual().nome


def _marca_html() -> str:
    """Wordmark da banda: o logo (PNG/JPEG para fundo escuro) ou o nome."""
    ident = identidade.atual()
    if ident.logo_url:
        return (
            f"<img src='{escape(ident.logo_url, quote=True)}' "
            f"alt='{escape(ident.nome, quote=True)}' "
            "height='28' style='display:block;height:28px;width:auto;border:0'>"
        )
    return escape(ident.nome).replace(" ", "&nbsp;")


def _tabela(selo: str, titulo: str, conteudo: str) -> str:
    c = _cores()
    ponto = (
        "<td width='14' style='vertical-align:middle'>"
        f"<div style='width:12px;height:12px;border-radius:50%;background:{c['acento']};"
        f"background:{c['grad']}'></div></td>"
        if not identidade.atual().logo_url
        else ""
    )
    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='background:{_BONE};padding:32px 12px'><tr><td align='center'>"
        "<table role='presentation' width='560' cellpadding='0' cellspacing='0' "
        "style='width:100%;max-width:560px'>"
        # ── banda da marca (header): banda + brand-dot + wordmark ──
        f"<tr><td style='background:{c['banda']};border-radius:14px 14px 0 0;"
        "padding:20px 28px'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        f"{ponto}"
        f"<td style='vertical-align:middle;padding-left:{10 if ponto else 0}px;font-family:{_MONO};"
        f"font-size:13px;letter-spacing:.14em;color:{_PAPER};text-transform:uppercase'>"
        f"{_marca_html()}</td>"
        f"<td align='right' style='vertical-align:middle;font-family:{_MONO};"
        f"font-size:10px;letter-spacing:.12em;color:{c['acento']};text-transform:uppercase'>"
        f"{selo}</td>"
        "</tr></table></td></tr>"
        # ── fio de gradiente (o .hairline-rule da marca) ──
        f"<tr><td style='height:3px;line-height:3px;font-size:0;background:{c['acento']};"
        f"background:{c['grad']}'>&nbsp;</td></tr>"
        # ── card de conteúdo (tema claro) ──
        f"<tr><td style='background:{_PAPER};border:1px solid {_HAIRLINE};"
        "border-top:0;border-radius:0 0 14px 14px;padding:28px'>"
        f"<h1 style='margin:0 0 14px;font-family:{_SANS};font-size:20px;"
        f"line-height:1.3;font-weight:600;color:{_INK}'>{titulo}</h1>"
        f"{conteudo}"
        "</td></tr>"
        # ── rodapé (metadata) ──
        f"<tr><td style='padding:18px 12px 0;text-align:center;font-family:{_SANS};"
        f"font-size:12px;line-height:1.6;color:{_INK3}'>"
        f"{escape(_nome())} — captação, repasses, conformidade e obras do seu território, "
        "num só painel.<br>Se você não solicitou este e-mail, ignore-o.</td></tr>"
        "</table></td></tr></table>"
    )


def _paragrafo(texto: str) -> str:
    return (
        f"<p style='margin:0 0 14px;font-family:{_SANS};font-size:15px;"
        f"line-height:1.6;color:{_INK2}'>{texto}</p>"
    )


def _apoio(texto: str) -> str:
    """Linha de apoio (metadata): expiração de link, observações."""
    return (
        f"<p style='margin:14px 0 0;font-family:{_SANS};font-size:12px;"
        f"line-height:1.6;color:{_INK3}'>{texto}</p>"
    )


def _botao(url: str, label: str) -> str:
    """Botão primário do design (--action-bg abyss, rótulo mono) + link cru de
    retaguarda — cliente que bloqueia o botão ainda chega ao destino."""
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' "
        "style='margin:20px 0 6px'><tr>"
        f"<td style='background:{_cores()['banda']};border-radius:10px'>"
        f"<a href='{url}' style='display:inline-block;padding:12px 22px;"
        f"font-family:{_MONO};font-size:13px;letter-spacing:.06em;"
        f"color:{_PAPER};text-decoration:none'>{label}</a>"
        "</td></tr></table>"
        f"<p style='margin:0 0 8px;font-family:{_SANS};font-size:12px;"
        f"line-height:1.6;color:{_INK3};word-break:break-all'>"
        f"Se o botão não abrir, copie e cole o link:<br>"
        f"<a href='{url}' style='color:{_INK3}'>{url}</a></p>"
    )


def _render(selo: str, titulo: str, conteudo: str, preheader: str) -> str:
    return _DOC.format(preheader=preheader, tabela=_tabela(selo, titulo, conteudo))


def boas_vindas(nome: str | None) -> tuple[str, str, str]:
    ola = f"Olá, {nome}!" if nome else "Bem-vindo(a)!"
    txt = (
        f"{ola}\n\nSua conta no {_nome()} foi criada. "
        "Acompanhe captação, repasses, conformidade e obras do seu território "
        "num só painel."
    )
    html = _render(
        selo="Conta criada",
        titulo=ola,
        conteudo=_paragrafo(
            f"Sua conta no {_nome()} foi criada. Acompanhe captação, repasses, "
            "conformidade e obras do seu território num só painel."
        )
        + _paragrafo(
            "O primeiro passo é o onboarding: escolha seu município e as áreas "
            "de interesse — o painel se monta a partir do seu território."
        ),
        preheader=f"Sua conta no {_nome()} foi criada.",
    )
    return f"Bem-vindo(a) ao {_nome()}", txt, html


def redefinir_senha(url: str) -> tuple[str, str, str]:
    txt = (
        "Recebemos um pedido para redefinir sua senha.\n\n"
        f"Abra o link para criar uma nova senha:\n{url}\n\n"
        "O link expira em 1 hora."
    )
    html = _render(
        selo="Segurança",
        titulo="Redefinir sua senha",
        conteudo=_paragrafo(
            "Recebemos um pedido para redefinir a senha da sua conta. "
            "Use o botão abaixo para criar uma nova."
        )
        + _botao(url, "Redefinir senha")
        + _apoio("O link expira em 1 hora."),
        preheader="Crie uma nova senha para a sua conta — o link expira em 1 hora.",
    )
    return f"Redefinir sua senha — {_nome()}", txt, html


def verificar_email(url: str) -> tuple[str, str, str]:
    txt = f"Confirme seu e-mail para ativar a conta:\n{url}"
    html = _render(
        selo="Confirmação",
        titulo="Confirme seu e-mail",
        conteudo=_paragrafo("Confirme seu endereço de e-mail para ativar a conta.")
        + _botao(url, "Confirmar e-mail"),
        preheader="Confirme seu e-mail para ativar a conta.",
    )
    return f"Confirme seu e-mail — {_nome()}", txt, html


def convite(url: str, papel: str | None) -> tuple[str, str, str]:
    papel_txt = f" como <b style='color:{_INK}'>{papel}</b>" if papel else ""
    txt = (
        f"Você foi convidado(a) para o {_nome()}{(' como ' + papel) if papel else ''}.\n\n"
        f"Aceite o convite e crie sua senha:\n{url}"
    )
    html = _render(
        selo="Convite",
        titulo="Você foi convidado(a)",
        conteudo=_paragrafo(
            f"Você foi convidado(a) para o {_nome()}{papel_txt} — o painel que "
            "concentra captação, repasses, conformidade e obras do seu território."
        )
        + _botao(url, "Aceitar convite")
        + _apoio("Ao aceitar, você cria sua senha e já entra no painel."),
        preheader=f"Aceite o convite e crie sua senha no {_nome()}.",
    )
    return f"Seu convite para o {_nome()}", txt, html


def alertas_resumo(linhas: list[str], url_painel: str | None) -> tuple[str, str, str]:
    """Resumo dos alertas novos (nova proposta / oportunidade / mudança)."""
    corpo = "\n".join(f"• {li}" for li in linhas)
    txt = "Novidades no seu território:\n\n" f"{corpo}\n\n" + (
        f"Veja no painel: {url_painel}" if url_painel else "Veja no painel do {_nome()}."
    )
    # Feed do painel: cada alerta é uma linha com o dot da marca e hairline
    # entre elas — o mesmo desenho da central de alertas.
    itens_html = "".join(
        "<tr>"
        "<td width='10' style='vertical-align:top;padding:10px 0'>"
        f"<div style='width:7px;height:7px;border-radius:50%;background:{_cores()['acento']};"
        f"background:{_cores()['grad']};margin-top:6px'></div></td>"
        f"<td style='padding:10px 0 10px 10px;font-family:{_SANS};font-size:14px;"
        f"line-height:1.55;color:{_INK2};"
        + (f"border-bottom:1px solid {_HAIRLINE}" if i < len(linhas) - 1 else "")
        + f"'>{li}</td></tr>"
        for i, li in enumerate(linhas)
    )
    lista = (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='margin:4px 0'>{itens_html}</table>"
    )
    botao = _botao(url_painel, "Abrir o painel") if url_painel else ""
    html = _render(
        selo="Alertas",
        titulo="Novidades no seu território",
        conteudo=_paragrafo("O monitoramento encontrou fatos novos nos seus municípios:")
        + lista
        + botao,
        preheader=(linhas[0] if linhas else "Novidades no seu território."),
    )
    return f"{_nome()} — novidades no seu território", txt, html
