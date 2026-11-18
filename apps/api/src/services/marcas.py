"""White label (§69) — marcas, resolução por host, CSS do tema e domínio próprio.

Três responsabilidades, todas aqui para a regra morar num lugar só:

1. **Qual marca é esta?** `por_host()` — o site pergunta pelo HOST
   (`marca.hubcapture.com.br` → slug; `painel.prefeitura.gov.br` → domínio
   próprio verificado). Host da plataforma (ou desconhecido) = Hub Capture.
2. **Como ela se veste?** `montar_css()` — PURO: do tema validado sai o CSS
   que redefine os tokens do design system (cores nos dois temas, raio,
   tipografia, traço dos ícones). Nada do que o dono digita vira CSS: só hex
   validado, item de catálogo e número da nossa tabela.
3. **O domínio próprio aponta para nós?** `verificar_dominio()` — resolve os
   dois nomes no DNS e compara os IPs (cobre CNAME e registro A de apex).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import socket
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.marca import TIPOS_ASSET, Marca, MarcaAsset
from ..models.usuario import Usuario
from ..schemas.marcas import (
    AssetInfo,
    BrandingRead,
    MarcaRead,
    ProvisionamentoHost,
    TemaMarca,
)
from . import config as config_service
from .identidade import ASSISTENTE_PADRAO, NOME_PADRAO, PADRAO, Identidade

log = logging.getLogger("hubcapture.marcas")

# ── Catálogos ───────────────────────────────────────────────────────────────

# Tipografia: catálogo FECHADO. As duas da casa vêm do repositório (§67b); as
# demais, do Google Fonts em RUNTIME (o build não baixa nada). `arquivo` usa a
# fonte .woff2 enviada pela marca.
_SANS_FALLBACK = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
_SERIF_FALLBACK = 'ui-serif, Georgia, "Times New Roman", serif'

FONTES: dict[str, dict] = {
    "inter": {"rotulo": "Inter (padrão)", "familia": 'var(--font-sans-src, "Inter"), "Inter"'},
    "archivo": {
        "rotulo": "Archivo (padrão dos títulos)",
        "familia": 'var(--font-display-src, "Archivo"), "Archivo"',
    },
    "sistema": {"rotulo": "Fonte do sistema", "familia": "system-ui"},
    "poppins": {"rotulo": "Poppins", "familia": '"Poppins"', "google": "Poppins"},
    "montserrat": {"rotulo": "Montserrat", "familia": '"Montserrat"', "google": "Montserrat"},
    "roboto": {"rotulo": "Roboto", "familia": '"Roboto"', "google": "Roboto"},
    "open-sans": {"rotulo": "Open Sans", "familia": '"Open Sans"', "google": "Open Sans"},
    "lato": {"rotulo": "Lato", "familia": '"Lato"', "google": "Lato", "pesos": "400;700"},
    "nunito": {"rotulo": "Nunito", "familia": '"Nunito"', "google": "Nunito"},
    "dm-sans": {"rotulo": "DM Sans", "familia": '"DM Sans"', "google": "DM Sans"},
    "manrope": {"rotulo": "Manrope", "familia": '"Manrope"', "google": "Manrope"},
    "plus-jakarta-sans": {
        "rotulo": "Plus Jakarta Sans",
        "familia": '"Plus Jakarta Sans"',
        "google": "Plus Jakarta Sans",
    },
    "work-sans": {"rotulo": "Work Sans", "familia": '"Work Sans"', "google": "Work Sans"},
    "ibm-plex-sans": {
        "rotulo": "IBM Plex Sans",
        "familia": '"IBM Plex Sans"',
        "google": "IBM Plex Sans",
    },
    "source-sans-3": {
        "rotulo": "Source Sans 3",
        "familia": '"Source Sans 3"',
        "google": "Source Sans 3",
    },
    "raleway": {"rotulo": "Raleway", "familia": '"Raleway"', "google": "Raleway"},
    "merriweather": {
        "rotulo": "Merriweather (serifada)",
        "familia": '"Merriweather"',
        "google": "Merriweather",
        "pesos": "400;700",
        "serifa": True,
    },
    "playfair-display": {
        "rotulo": "Playfair Display (serifada)",
        "familia": '"Playfair Display"',
        "google": "Playfair Display",
        "serifa": True,
    },
    "arquivo": {"rotulo": "Arquivo enviado (.woff2)", "familia": None},
}

# Forma: raio dos cards/controles + a escala do Tailwind (`rounded-lg` lê
# `--radius-lg`). "padrao" não emite nada — o raio do design system.
FORMAS: dict[str, dict] = {
    "reta": {
        "rotulo": "Reta",
        "raios": {"card": 2, "control": 2, "sm": 1, "md": 2, "lg": 2, "xl": 3, "2xl": 4, "3xl": 4},
    },
    "padrao": {"rotulo": "Padrão", "raios": {}},
    "suave": {
        "rotulo": "Suave",
        "raios": {"card": 14, "control": 8, "lg": 10, "xl": 14, "2xl": 18, "3xl": 24},
    },
    "arredondada": {
        "rotulo": "Arredondada",
        "raios": {
            "card": 20,
            "control": 12,
            "sm": 6,
            "md": 8,
            "lg": 14,
            "xl": 18,
            "2xl": 24,
            "3xl": 30,
        },
    },
    "pilula": {
        "rotulo": "Pílula (botões redondos)",
        "raios": {
            "card": 24,
            "control": 999,
            "sm": 8,
            "md": 10,
            "lg": 16,
            "xl": 22,
            "2xl": 28,
            "3xl": 32,
        },
    },
}

TRACOS = {"fino": ("Fino", 1.25), "regular": ("Regular", 1.5), "grosso": ("Grosso", 2.0)}

ROTULO_ASSET = {
    "logo": "Logo (fundo claro)",
    "logo_escuro": "Logo (fundo escuro)",
    "icone": "Ícone do app (favicon, tela de início)",
    "login_imagem": "Imagem da tela de login",
    "fonte_corpo": "Fonte do corpo (.woff2)",
    "fonte_titulo": "Fonte dos títulos (.woff2)",
}

# o que cada tipo de arquivo aceita (tipo MIME → extensão) e o teto de tamanho
_IMAGENS = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
_ACEITOS: dict[str, set[str]] = {
    "logo": _IMAGENS,
    "logo_escuro": _IMAGENS,
    "icone": {"image/png", "image/svg+xml"},
    "login_imagem": {"image/png", "image/jpeg", "image/webp"},
    "fonte_corpo": {"font/woff2"},
    "fonte_titulo": {"font/woff2"},
}
_TETO_BYTES = {"login_imagem": 4 * 1024 * 1024}
_TETO_PADRAO = 1024 * 1024

# subdomínios que NUNCA viram marca (infra, painel, sandbox…)
SLUGS_RESERVADOS = frozenset(
    {
        "www",
        "app",
        "api",
        "admin",
        "sandbox",
        "mail",
        "smtp",
        "imap",
        "pop",
        "static",
        "cdn",
        "assets",
        "docs",
        "status",
        "dev",
        "staging",
        "homolog",
        "hub",
        "painel",
        "n8n",
        "traefik",
        "dokploy",
        "ns1",
        "ns2",
        "ftp",
        "blog",
        "suporte",
        "help",
    }
)
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")
_ROTULO_DNS = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


# ── Cores (puro) ────────────────────────────────────────────────────────────


def _rgb(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def misturar(a: str, b: str, peso_a: float) -> str:
    """`peso_a` de A sobre (1-peso_a) de B — o color-mix do CSS, feito aqui
    para o e-mail e o PDF (que não têm color-mix) usarem o MESMO tom."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(peso_a * x + (1 - peso_a) * y for x, y in zip(ra, rb, strict=True)))


def _luminancia(hexa: str) -> float:
    def canal(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in _rgb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tinta_sobre(fundo: str, escuro: str = "#031918") -> str:
    """Tinta legível sobre `fundo`: branco ou o escuro da marca, o que tiver
    mais contraste (é o --fill-accent-fg/--brand-fg que a marca não escolhe)."""
    return "#ffffff" if contraste(fundo, "#ffffff") >= contraste(fundo, escuro) else escuro


def _rgba(hexa: str, alfa: float) -> str:
    r, g, b = _rgb(hexa)
    return f"rgba({r}, {g}, {b}, {alfa})"


# ── CSS do tema (puro) ──────────────────────────────────────────────────────


def _familia(chave: str, papel: str, enviadas: dict[str, str]) -> str | None:
    """Pilha CSS da fonte. None = não sobrescrever (padrão do design system)."""
    if chave == "arquivo":
        return f'"Marca{papel.title()}", {_SANS_FALLBACK}' if papel in enviadas else None
    meta = FONTES.get(chave) or {}
    base = meta.get("familia")
    if not base:
        return None
    return f"{base}, {_SERIF_FALLBACK if meta.get('serifa') else _SANS_FALLBACK}"


def fontes_google(tema: TemaMarca) -> list[str]:
    """URL do Google Fonts para as fontes do catálogo que vêm de lá (uma só)."""
    familias: list[str] = []
    for chave in dict.fromkeys((tema.fonte_corpo, tema.fonte_titulo)):
        meta = FONTES.get(chave) or {}
        if meta.get("google"):
            nome = meta["google"].replace(" ", "+")
            familias.append(f"family={nome}:wght@{meta.get('pesos', '400;500;600;700')}")
    if not familias:
        return []
    return ["https://fonts.googleapis.com/css2?" + "&".join(familias) + "&display=swap"]


def _bloco(seletor: str, tokens: dict[str, str]) -> str:
    if not tokens:
        return ""
    corpo = "".join(f"{k}:{v};" for k, v in tokens.items())
    return f"{seletor}{{{corpo}}}"


def montar_css(
    tema: TemaMarca,
    *,
    seletor: str = ":root",
    fontes_enviadas: dict[str, str] | None = None,
) -> str:
    """CSS que veste o design system com o tema da marca.

    `seletor=":root"` é o site; `".marca-preview"` é a pré-visualização do
    editor (escopada, para o admin não pintar o próprio painel enquanto edita).
    `fontes_enviadas` = {"corpo"|"titulo": url do .woff2}.
    """
    enviadas = fontes_enviadas or {}
    cores = tema.cores
    claro: dict[str, str] = {}
    escuro_tk: dict[str, str] = {}

    A, E, C = cores.acento, cores.escuro, cores.acao
    base_escura = E or "#031918"

    if A:
        suave = misturar(A, "#ffffff", 0.18)
        tinta_a = tinta_sobre(A, base_escura)
        claro.update(
            {
                "--color-accent": A,
                "--color-lime": A,
                "--color-aqua": A,
                "--color-accent-soft": suave,
                "--fill-accent": A,
                "--fill-accent-fg": tinta_a,
                "--bar-2": A,
                "--bar-1": misturar(A, "#ffffff", 0.3),
                "--nav-active-bg": suave,
                "--ok-bg": suave,
                "--grad-brand": (
                    f"linear-gradient(135deg, {suave} 0%, "
                    f"{misturar(A, '#ffffff', 0.07)} 55%, #ffffff 100%)"
                ),
            }
        )
        escuro_tk.update(
            {
                "--brand": A,
                "--brand-fg": tinta_a,
                "--brand-hover": misturar(A, "#ffffff", 0.82),
                "--action-bg": A,
                "--action-fg": tinta_a,
                "--ok": A,
                "--ok-bg": _rgba(A, 0.14),
                "--bar-2": A,
                "--bar-3": misturar(A, "#ffffff", 0.6),
                "--fill-accent": A,
                "--fill-accent-fg": tinta_a,
                "--nav-active-bg": _rgba(A, 0.12),
                "--nav-active-ink": A,
                "--grad-brand": (
                    f"linear-gradient(135deg, {_rgba(A, 0.22)} 0%, "
                    f"{_rgba(A, 0.07)} 55%, transparent 100%)"
                ),
                "--grad-text": f"linear-gradient(120deg, {A}, {misturar(A, '#ffffff', 0.6)})",
            }
        )
    if C:
        claro.update(
            {
                "--brand": C,
                "--color-brand-600": C,
                "--color-brand-700": misturar(C, "#000000", 0.9),
                "--brand-fg": tinta_sobre(C, base_escura),
                "--brand-hover": misturar(C, "#000000", 0.9),
                "--action-bg": C,
                "--action-fg": tinta_sobre(C, base_escura),
                "--ok": C,
                "--ok-solid": C,
                "--ok-solid-fg": tinta_sobre(C, base_escura),
                "--bar-3": C,
                "--nav-active-ink": C,
            }
        )
        escuro_tk["--ok-solid"] = C
        escuro_tk["--ok-solid-fg"] = tinta_sobre(C, base_escura)
    if E:
        claro.update(
            {
                "--color-brand-dark": E,
                "--color-abyss": E,
                "--nav-brand-ink": E,
                "--warn-solid-fg": E,
                "--grad-text": f"linear-gradient(120deg, {E}, {C or misturar(E, '#ffffff', 0.7)})",
                # neutros do claro levemente tingidos pela marca (o canvas
                # esverdeado do Hub ficaria estranho ao lado de um azul)
                "--surface": misturar(E, "#ffffff", 0.045),
                "--surface-2": misturar(E, "#ffffff", 0.07),
                "--surface-3": misturar(E, "#ffffff", 0.12),
                "--hairline": misturar(E, "#ffffff", 0.12),
                "--hairline-strong": misturar(E, "#ffffff", 0.2),
                "--nav-hover-bg": misturar(E, "#ffffff", 0.07),
                "--nav-surface": misturar(E, "#ffffff", 0.045),
                "--nav-hairline": misturar(E, "#ffffff", 0.12),
            }
        )
        escuro_tk.update(
            {
                "--surface": misturar("#ffffff", E, 0.03),
                "--surface-2": misturar("#ffffff", E, 0.09),
                "--surface-3": misturar("#ffffff", E, 0.13),
                "--card": misturar("#ffffff", E, 0.06),
                "--card-border": misturar("#ffffff", E, 0.11),
                "--glass": misturar("#ffffff", E, 0.06),
                "--hairline": misturar("#ffffff", E, 0.11),
                "--hairline-strong": misturar("#ffffff", E, 0.19),
                "--nav-bg": E,
                "--nav-menu-bg": misturar("#ffffff", E, 0.05),
                "--grad-card": (
                    f"linear-gradient(180deg, {misturar('#ffffff', E, 0.075)} 0%, "
                    f"{misturar('#ffffff', E, 0.06)} 100%)"
                ),
            }
        )

    raios = FORMAS.get(tema.forma, {}).get("raios", {})
    for nome, px in raios.items():
        claro[f"--radius-{nome}"] = f"{px}px"

    corpo = _familia(tema.fonte_corpo, "corpo", enviadas)
    titulo = _familia(tema.fonte_titulo, "titulo", enviadas)
    if corpo and tema.fonte_corpo != "inter":
        claro["--font-sans"] = corpo
        claro["--font-mono"] = corpo  # o "mono" do sistema é a face do corpo (§57)
    if titulo and tema.fonte_titulo != "archivo":
        claro["--font-display"] = titulo

    traco = TRACOS.get(tema.icones, TRACOS["regular"])[1]
    if tema.icones != "regular" or tema.icones_cantos != "arredondado":
        claro["--icon-stroke"] = f"{traco}"
        claro["--icon-cap"] = "round" if tema.icones_cantos == "arredondado" else "square"
        claro["--icon-join"] = "round" if tema.icones_cantos == "arredondado" else "miter"

    partes: list[str] = []
    for papel, url in enviadas.items():
        partes.append(
            f'@font-face{{font-family:"Marca{papel.title()}";src:url("{url}") format("woff2");'
            "font-weight:100 900;font-style:normal;font-display:swap}"
        )

    preview = seletor != ":root"
    if preview:
        # Na pré-visualização os aliases do @theme (calculados no :root)
        # precisam ser religados no escopo, senão herdariam o valor do site.
        claro.update(
            {
                "--color-brand": "var(--brand)",
                "--color-brand-fg": "var(--brand-fg)",
                "--color-ok": "var(--ok)",
                "--color-ok-bg": "var(--ok-bg)",
                "--color-surface": "var(--surface)",
                "--color-surface-2": "var(--surface-2)",
                "--color-surface-3": "var(--surface-3)",
                "--color-card": "var(--card)",
                "--color-hairline": "var(--hairline)",
            }
        )

    # No site, `html:root` (e não `:root`): especificidade UM degrau acima da
    # de cada bloco do globals.css, então a marca vence sem depender da ORDEM
    # em que o Next/React insere as folhas de estilo no <head>. O claro
    # (0,1,1) continua abaixo dos blocos escuros do globals (0,2,0), e os
    # escuros da marca (0,2,1) acima deles — a mesma escada, um degrau acima.
    raiz = seletor if preview else "html:root"
    partes.append(_bloco(raiz, claro))
    if escuro_tk:
        if preview:
            sel_media = f':root:not([data-theme="light"]) {seletor}'
            sel_forcado = f':root[data-theme="dark"] {seletor}'
        else:
            sel_media = 'html:root:not([data-theme="light"])'
            sel_forcado = 'html:root[data-theme="dark"]'
        partes.append(f"@media (prefers-color-scheme: dark){{{_bloco(sel_media, escuro_tk)}}}")
        partes.append(_bloco(sel_forcado, escuro_tk))

    alvo = f"{seletor} " if preview else "html "
    if preview:
        partes.append(f"{seletor}{{font-family:var(--font-sans)}}")
    if not tema.titulos_caixa_alta:
        sel = ",".join(
            f"{alvo}{s}"
            for s in (
                "h1",
                "h2",
                "h3",
                ".page-title",
                ".sidebar-brand",
                ".stat-label",
                ".box-title",
            )
        )
        partes.append(f"{sel}{{text-transform:none;letter-spacing:-0.01em}}")
    if "--icon-stroke" in claro:
        sel = f"{alvo}.nav-icon,{alvo}svg.icone"
        partes.append(
            f"{sel}{{stroke-width:var(--icon-stroke);stroke-linecap:var(--icon-cap);"
            "stroke-linejoin:var(--icon-join)}"
        )
    return "".join(p for p in partes if p)


def avisos_de_contraste(tema: TemaMarca) -> list[str]:
    """Alertas de legibilidade para o editor (não bloqueiam o salvar)."""
    avisos: list[str] = []
    c = tema.cores
    if c.acao and contraste(c.acao, "#ffffff") < 4.5:
        avisos.append(
            "A cor de ação tem pouco contraste sobre o branco "
            f"({contraste(c.acao, '#ffffff'):.1f}:1, o mínimo legível é 4,5:1) — "
            "links e botões podem ficar difíceis de ler no tema claro."
        )
    if c.escuro and contraste(c.escuro, "#ffffff") < 7:
        avisos.append(
            "O tom escuro está claro demais para o trilho e o tema escuro — "
            "texto branco sobre ele perde leitura."
        )
    if c.acento and c.escuro and contraste(c.acento, c.escuro) < 3:
        avisos.append(
            "O acento quase não se destaca do tom escuro — no tema escuro, o item "
            "ativo e o foco ficam apagados."
        )
    return avisos


# ── Domínio-base, hosts e URLs ──────────────────────────────────────────────


async def dominio_base() -> str:
    valor = await config_service.resolver("whitelabel_dominio_base")
    return (valor or settings.whitelabel_dominio_base or "hubcapture.com.br").strip().lower()


def normalizar_host(host: str | None) -> str:
    """'Painel.Exemplo.com.br:443.' → 'painel.exemplo.com.br'. Pega só o 1º
    valor de um X-Forwarded-Host encadeado."""
    h = (host or "").split(",")[0].strip().lower()
    if h.startswith("["):  # IPv6 literal
        return ""
    h = h.split(":")[0].rstrip(".")
    return h


def validar_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not _SLUG.match(s) or "--" in s:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "SLUG_INVALIDO: use 3 a 63 letras minúsculas, números ou hífen "
            "(sem hífen no começo/fim).",
        )
    if s in SLUGS_RESERVADOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"SLUG_RESERVADO: {s}")
    return s


def validar_dominio(dominio: str, base: str) -> str:
    d = normalizar_host(dominio.removeprefix("https://").removeprefix("http://").split("/")[0])
    try:
        d = d.encode("idna").decode("ascii")  # acento vira punycode
    except UnicodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "DOMINIO_INVALIDO") from exc
    rotulos = d.split(".")
    if len(rotulos) < 2 or not all(_ROTULO_DNS.match(r) for r in rotulos) or len(d) > 253:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "DOMINIO_INVALIDO")
    if d == base or d.endswith("." + base):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"DOMINIO_DA_PLATAFORMA: subdomínios de {base} já são o endereço padrão da marca.",
        )
    return d


def host_padrao(marca: Marca, base: str) -> str:
    return f"{marca.slug}.{base}"


async def cname_alvo(marca: Marca, base: str | None = None) -> str:
    """Para onde o CNAME do cliente deve apontar. Padrão: o próprio subdomínio
    da marca; `whitelabel_cname_alvo` fixa um alvo único (ex.: um host de
    borda) quando a operação preferir."""
    base = base or await dominio_base()
    fixo = (await config_service.resolver("whitelabel_cname_alvo") or "").strip().lower()
    return fixo or host_padrao(marca, base)


def url_publica(marca: Marca, base: str) -> str:
    if marca.dominio and marca.dominio_status == "ativo":
        return f"https://{marca.dominio}"
    return f"https://{host_padrao(marca, base)}"


def _asset_url(marca_id: uuid.UUID, tipo: str, hash_: str) -> str:
    return f"/api/v1/branding/assets/{marca_id}/{tipo}?v={hash_[:12]}"


# ── Cache de resolução (host → branding) ────────────────────────────────────

_TTL = 30.0
_cache_host: dict[str, tuple[float, uuid.UUID | None]] = {}
_cache_identidade: dict[uuid.UUID, tuple[float, Identidade]] = {}


def limpar_cache() -> None:
    _cache_host.clear()
    _cache_identidade.clear()


async def _marca_por_host(session: AsyncSession, host: str) -> Marca | None:
    h = normalizar_host(host)
    if not h:
        return None
    agora = time.monotonic()
    hit = _cache_host.get(h)
    if hit and hit[0] > agora:
        return await session.get(Marca, hit[1]) if hit[1] else None

    base = await dominio_base()
    marca: Marca | None = None
    if h.endswith("." + base):
        rotulo = h[: -(len(base) + 1)]
        if rotulo and "." not in rotulo and rotulo not in SLUGS_RESERVADOS:
            marca = (
                await session.execute(select(Marca).where(Marca.slug == rotulo))
            ).scalar_one_or_none()
    elif h != base:
        marca = (
            await session.execute(
                select(Marca).where(
                    Marca.dominio == h, Marca.dominio_status.in_(("verificado", "ativo"))
                )
            )
        ).scalar_one_or_none()
    if marca is not None and not marca.ativo:
        marca = None
    _cache_host[h] = (agora + _TTL, marca.id if marca else None)
    return marca


async def por_host(session: AsyncSession, host: str | None) -> Marca | None:
    """A marca deste host, ou None (= Hub Capture). Marca desativada = None."""
    return await _marca_por_host(session, host or "")


async def _assets(session: AsyncSession, marca_id: uuid.UUID) -> list[MarcaAsset]:
    rows = await session.execute(
        select(
            MarcaAsset.id,
            MarcaAsset.tipo,
            MarcaAsset.content_type,
            MarcaAsset.tamanho,
            MarcaAsset.hash,
            MarcaAsset.nome_arquivo,
        ).where(MarcaAsset.marca_id == marca_id)
    )
    return list(rows.all())  # type: ignore[arg-type]


def tema_de(marca: Marca | None) -> TemaMarca:
    try:
        return TemaMarca.model_validate((marca.tema if marca else None) or {})
    except Exception:  # noqa: BLE001 — tema gravado inválido nunca derruba o site
        log.warning("marca %s com tema inválido no banco; usando padrão", marca and marca.id)
        return TemaMarca()


def branding_padrao() -> BrandingRead:
    return BrandingRead(
        personalizada=False,
        nome=NOME_PADRAO,
        assistente=ASSISTENTE_PADRAO,
        tema=TemaMarca(),
        css="",
        cor_tema_claro="#f3f7f5",
        cor_tema_escuro="#08201e",
    )


async def branding(session: AsyncSession, marca: Marca | None) -> BrandingRead:
    if marca is None:
        return branding_padrao()
    tema = tema_de(marca)
    assets = {a.tipo: a for a in await _assets(session, marca.id)}
    url = {tipo: _asset_url(marca.id, tipo, a.hash) for tipo, a in assets.items()}
    enviadas = {
        papel: url[f"fonte_{papel}"] for papel in ("corpo", "titulo") if f"fonte_{papel}" in url
    }
    css = montar_css(tema, fontes_enviadas=enviadas)
    E = tema.cores.escuro
    return BrandingRead(
        personalizada=True,
        id=marca.id,
        slug=marca.slug,
        nome=tema.nome_exibicao or marca.nome,
        assistente=tema.nome_assistente or ASSISTENTE_PADRAO,
        tema=tema,
        css=css,
        fontes_urls=fontes_google(tema),
        logo_url=url.get("logo"),
        logo_escuro_url=url.get("logo_escuro"),
        icone_url=url.get("icone"),
        login_imagem_url=url.get("login_imagem"),
        cadastro_aberto=marca.cadastro_aberto,
        cor_tema_claro=misturar(E, "#ffffff", 0.045) if E else "#f3f7f5",
        cor_tema_escuro=misturar("#ffffff", E, 0.03) if E else "#08201e",
    )


# ── Identidade para superfícies externas (e-mail, PDF, push, Copiloto) ──────


async def identidade(session: AsyncSession, marca_id: uuid.UUID | None) -> Identidade:
    if marca_id is None:
        return PADRAO
    agora = time.monotonic()
    hit = _cache_identidade.get(marca_id)
    if hit and hit[0] > agora:
        return hit[1]
    marca = await session.get(Marca, marca_id)
    if marca is None or not marca.ativo:
        ident = PADRAO
    else:
        tema = tema_de(marca)
        base = await dominio_base()
        url_base = url_publica(marca, base)
        logo = (
            (
                await session.execute(
                    select(MarcaAsset).where(
                        MarcaAsset.marca_id == marca.id,
                        MarcaAsset.tipo.in_(("logo_escuro", "logo")),
                        MarcaAsset.content_type.in_(("image/png", "image/jpeg")),
                    )
                )
            )
            .scalars()
            .all()
        )
        # e-mail e PDF põem o logo sobre a BANDA ESCURA: a versão para fundo
        # escuro vence; SVG/WebP ficam de fora (Outlook/Gmail e o reportlab
        # não desenham) e a banda cai para o nome por extenso.
        escolhido = next((a for a in logo if a.tipo == "logo_escuro"), None) or next(
            (a for a in logo if a.tipo == "logo"), None
        )
        cores = tema.cores
        ident = Identidade(
            nome=tema.nome_exibicao or marca.nome,
            assistente=tema.nome_assistente or ASSISTENTE_PADRAO,
            acento=cores.acento or PADRAO.acento,
            escuro=cores.escuro or PADRAO.escuro,
            acao=cores.acao or PADRAO.acao,
            url_base=url_base,
            logo_url=(
                f"{url_base}{_asset_url(marca.id, escolhido.tipo, escolhido.hash)}"
                if escolhido
                else None
            ),
            logo_bytes=escolhido.conteudo if escolhido else None,
            marca_id=str(marca.id),
            padrao=False,
        )
    _cache_identidade[marca_id] = (agora + 60.0, ident)
    return ident


async def identidade_do_usuario(session: AsyncSession, usuario: Usuario | None) -> Identidade:
    return await identidade(session, getattr(usuario, "marca_id", None))


async def identidade_da_requisicao(
    session: AsyncSession, host: str | None, usuario: Usuario | None
) -> Identidade:
    """Dentro do site (PDF baixado, Copiloto) vale a marca do HOST — é o que a
    tela mostra; sem marca no host, a da conta."""
    marca = await por_host(session, host)
    if marca is not None:
        return await identidade(session, marca.id)
    return await identidade_do_usuario(session, usuario)


def host_da_requisicao(headers) -> str:  # noqa: ANN001 — Mapping de headers
    """Host ORIGINAL do navegador: o proxy da web (rewrite do Next) e o Traefik
    repassam em X-Forwarded-Host; o Host que chega à API é o interno."""
    return normalizar_host(headers.get("x-forwarded-host") or headers.get("host"))


# ── CRUD ────────────────────────────────────────────────────────────────────


async def _usuario_por_email(session: AsyncSession, email: str) -> Usuario:
    u = (
        await session.execute(select(Usuario).where(func.lower(Usuario.email) == email.lower()))
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "DONO_NAO_ENCONTRADO: cadastre a conta antes"
        )
    return u


async def criar(
    session: AsyncSession,
    *,
    slug: str,
    nome: str,
    dono_email: str | None,
    plano_id: uuid.UUID | None,
    tema: TemaMarca | None,
) -> Marca:
    s = validar_slug(slug)
    if (await session.execute(select(Marca.id).where(Marca.slug == s))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "SLUG_EM_USO")
    dono = await _usuario_por_email(session, dono_email) if dono_email else None
    marca = Marca(
        slug=s,
        nome=nome.strip(),
        dono_id=dono.id if dono else None,
        plano_id=plano_id,
        tema=(tema or TemaMarca()).model_dump(mode="json", exclude_defaults=True),
        provisionamento={},
    )
    session.add(marca)
    await session.flush()
    if dono is not None and dono.marca_id is None:
        # o dono passa a assinar pela marca dele (e-mail, PDF, Copiloto)
        await session.execute(
            update(Usuario).where(Usuario.id == dono.id).values(marca_id=marca.id)
        )
    limpar_cache()
    return marca


async def atualizar(session: AsyncSession, marca: Marca, dados, *, admin: bool) -> Marca:  # noqa: ANN001
    campos_admin = {
        "slug": dados.slug,
        "ativo": dados.ativo,
        "dono_email": dados.dono_email,
        "plano_id": dados.plano_id,
    }
    tocou_admin = (
        any(v is not None for v in campos_admin.values())
        or dados.remover_dono
        or dados.remover_plano
    )
    if tocou_admin and not admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SO_ADMIN: slug, ativação, dono e plano")

    if dados.nome is not None:
        marca.nome = dados.nome.strip()
    if dados.tema is not None:
        marca.tema = dados.tema.model_dump(mode="json", exclude_defaults=True)
    if dados.cadastro_aberto is not None:
        marca.cadastro_aberto = dados.cadastro_aberto
    if admin:
        if dados.slug is not None and dados.slug != marca.slug:
            novo = validar_slug(dados.slug)
            if (await session.execute(select(Marca.id).where(Marca.slug == novo))).first():
                raise HTTPException(status.HTTP_409_CONFLICT, "SLUG_EM_USO")
            marca.slug = novo
        if dados.ativo is not None:
            marca.ativo = dados.ativo
        if dados.remover_dono:
            marca.dono_id = None
        elif dados.dono_email is not None:
            dono = await _usuario_por_email(session, str(dados.dono_email))
            marca.dono_id = dono.id
            if dono.marca_id is None:
                await session.execute(
                    update(Usuario).where(Usuario.id == dono.id).values(marca_id=marca.id)
                )
        if dados.remover_plano:
            marca.plano_id = None
        elif dados.plano_id is not None:
            marca.plano_id = dados.plano_id
    await session.flush()
    limpar_cache()
    return marca


async def obter_editavel(session: AsyncSession, marca_id: uuid.UUID, usuario: Usuario) -> Marca:
    """A marca, se `usuario` pode editá-la (dono ou admin). Sem permissão, 404 —
    não confirma que a marca existe."""
    marca = await session.get(Marca, marca_id)
    if marca is None or not (usuario.is_superuser or marca.dono_id == usuario.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MARCA_NAO_ENCONTRADA")
    return marca


async def ler(session: AsyncSession, marca: Marca) -> MarcaRead:
    base = await dominio_base()
    dono_email = None
    if marca.dono_id:
        dono_email = (
            await session.execute(select(Usuario.email).where(Usuario.id == marca.dono_id))
        ).scalar_one_or_none()
    membros = (
        await session.execute(select(func.count(Usuario.id)).where(Usuario.marca_id == marca.id))
    ).scalar_one()
    assets = [
        AssetInfo(
            tipo=a.tipo,
            url=_asset_url(marca.id, a.tipo, a.hash),
            content_type=a.content_type,
            tamanho=a.tamanho,
            nome_arquivo=a.nome_arquivo,
        )
        for a in await _assets(session, marca.id)
    ]
    prov = [
        ProvisionamentoHost(
            host=h, **{k: v for k, v in (d or {}).items() if k in ("status", "detalhe", "em")}
        )
        for h, d in (marca.provisionamento or {}).items()
    ]
    return MarcaRead(
        id=marca.id,
        slug=marca.slug,
        nome=marca.nome,
        ativo=marca.ativo,
        cadastro_aberto=marca.cadastro_aberto,
        dono_id=marca.dono_id,
        dono_email=dono_email,
        plano_id=marca.plano_id,
        tema=tema_de(marca),
        host_padrao=host_padrao(marca, base),
        url=url_publica(marca, base),
        dominio=marca.dominio,
        dominio_status=marca.dominio_status,
        dominio_detalhe=marca.dominio_detalhe,
        dominio_verificado_em=marca.dominio_verificado_em,
        cname_alvo=await cname_alvo(marca, base),
        provisionamento=prov,
        assets=assets,
        membros=membros,
        created_at=marca.created_at,
    )


# ── Arquivos ────────────────────────────────────────────────────────────────


def _tipo_real(conteudo: bytes, declarado: str | None, nome: str | None) -> str | None:
    """O tipo pelos BYTES (assinatura), não pelo que o navegador declarou —
    um HTML renomeado para .png não pode ser servido como imagem."""
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if conteudo[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"
    if conteudo[:4] == b"wOF2":
        return "font/woff2"
    cabeca = conteudo[:1024].lstrip().lower()
    if cabeca.startswith(b"<svg") or (
        cabeca.startswith(b"<?xml") and b"<svg" in conteudo[:4096].lower()
    ):
        return "image/svg+xml"
    return None


def sanitizar_svg(conteudo: bytes) -> bytes:
    """Remove o que executa num SVG (script, handlers on*, javascript:, objetos
    estrangeiros). Defesa em profundidade: o SVG também sai com CSP `sandbox`."""
    texto = conteudo.decode("utf-8", errors="replace")
    texto = re.sub(r"(?is)<script\b.*?</script\s*>", "", texto)
    texto = re.sub(r"(?is)<script\b[^>]*/>", "", texto)
    texto = re.sub(r"(?is)<foreignObject\b.*?</foreignObject\s*>", "", texto)
    texto = re.sub(r"(?i)\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", texto)
    texto = re.sub(
        r"(?i)(href|xlink:href)\s*=\s*([\"'])\s*javascript:[^\"']*\2", r"\1=\2#\2", texto
    )
    return texto.encode("utf-8")


async def salvar_asset(
    session: AsyncSession,
    marca: Marca,
    tipo: str,
    conteudo: bytes,
    nome_arquivo: str | None,
    declarado: str | None,
) -> AssetInfo:
    if tipo not in TIPOS_ASSET:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"TIPO_ASSET_INVALIDO: {tipo}")
    teto = _TETO_BYTES.get(tipo, _TETO_PADRAO)
    if not conteudo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ARQUIVO_VAZIO")
    if len(conteudo) > teto:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"ARQUIVO_GRANDE: limite de {teto // (1024 * 1024)} MB "
            f"para {ROTULO_ASSET[tipo].lower()}",
        )
    real = _tipo_real(conteudo, declarado, nome_arquivo)
    if real is None or real not in _ACEITOS[tipo]:
        aceitos = ", ".join(
            sorted(t.split("/")[1].replace("svg+xml", "svg") for t in _ACEITOS[tipo])
        )
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"FORMATO_NAO_ACEITO: use {aceitos}"
        )
    if real == "image/svg+xml":
        conteudo = sanitizar_svg(conteudo)
    h = hashlib.sha256(conteudo).hexdigest()
    existente = (
        await session.execute(
            select(MarcaAsset).where(MarcaAsset.marca_id == marca.id, MarcaAsset.tipo == tipo)
        )
    ).scalar_one_or_none()
    if existente is None:
        existente = MarcaAsset(marca_id=marca.id, tipo=tipo)
        session.add(existente)
    existente.content_type = real
    existente.conteudo = conteudo
    existente.tamanho = len(conteudo)
    existente.hash = h
    existente.nome_arquivo = (nome_arquivo or "")[:255] or None
    await session.flush()
    limpar_cache()
    return AssetInfo(
        tipo=tipo,
        url=_asset_url(marca.id, tipo, h),
        content_type=real,
        tamanho=len(conteudo),
        nome_arquivo=existente.nome_arquivo,
    )


async def remover_asset(session: AsyncSession, marca: Marca, tipo: str) -> None:
    a = (
        await session.execute(
            select(MarcaAsset).where(MarcaAsset.marca_id == marca.id, MarcaAsset.tipo == tipo)
        )
    ).scalar_one_or_none()
    if a is not None:
        await session.delete(a)
        await session.flush()
    limpar_cache()


async def ler_asset(session: AsyncSession, marca_id: uuid.UUID, tipo: str) -> MarcaAsset | None:
    return (
        await session.execute(
            select(MarcaAsset)
            .join(Marca, Marca.id == MarcaAsset.marca_id)
            .where(MarcaAsset.marca_id == marca_id, MarcaAsset.tipo == tipo, Marca.ativo.is_(True))
        )
    ).scalar_one_or_none()


# ── Domínio próprio ─────────────────────────────────────────────────────────


def _ips(host: str) -> set[str]:
    try:
        return {info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        return set()


async def resolver_ips(host: str) -> set[str]:
    """IPs do host pelo resolvedor do sistema, em thread e com teto de tempo
    (getaddrinfo é bloqueante e não tem timeout próprio)."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_ips, host), timeout=8)
    except TimeoutError:
        return set()


def comparar_dns(ips_dominio: set[str], ips_alvo: set[str]) -> tuple[bool, str]:
    """Puro: o domínio aponta para nós? Todos os IPs dele precisam estar entre
    os do alvo — um A extra (servidor antigo) faria parte dos visitantes cair
    em outro lugar, e o certificado nunca seria emitido de forma estável."""
    if not ips_dominio:
        return (
            False,
            "O domínio ainda não resolve no DNS (o registro pode levar até algumas horas).",
        )
    if not ips_alvo:
        return False, "O endereço de destino não resolveu agora — tente de novo em instantes."
    fora = ips_dominio - ips_alvo
    if fora:
        return False, (
            "O domínio aponta para outro servidor ("
            + ", ".join(sorted(fora))
            + "). Ajuste o CNAME e remova registros A/AAAA antigos."
        )
    return True, "DNS conferido: o domínio aponta para a plataforma."


async def definir_dominio(session: AsyncSession, marca: Marca, dominio: str | None) -> str | None:
    """Troca o domínio próprio (None remove). Devolve o host ANTIGO, para o
    chamador desprovisionar."""
    antigo = marca.dominio
    if not dominio:
        marca.dominio = None
        marca.dominio_status = None
        marca.dominio_detalhe = None
        marca.dominio_verificado_em = None
    else:
        base = await dominio_base()
        d = validar_dominio(dominio, base)
        if d != marca.dominio:
            dono = (await session.execute(select(Marca.id).where(Marca.dominio == d))).first()
            if dono:
                raise HTTPException(status.HTTP_409_CONFLICT, "DOMINIO_EM_USO")
            marca.dominio = d
            marca.dominio_status = "pendente"
            marca.dominio_detalhe = None
            marca.dominio_verificado_em = None
    await session.flush()
    limpar_cache()
    return antigo if antigo != marca.dominio else None


def registrar_provisionamento(marca: Marca, host: str, st: str, detalhe: str | None) -> None:
    prov = dict(marca.provisionamento or {})
    prov[host] = {"status": st, "detalhe": detalhe, "em": datetime.now(UTC).isoformat()}
    marca.provisionamento = prov  # nova referência: o SQLAlchemy só vê troca


async def membros(session: AsyncSession, marca: Marca) -> list[Usuario]:
    rows = await session.execute(
        select(Usuario).where(Usuario.marca_id == marca.id).order_by(Usuario.created_at.desc())
    )
    return list(rows.scalars().all())
