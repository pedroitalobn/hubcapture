"""Preparo do anexo para o WhatsApp — o que muda entre "documento" e "imagem".

A escolha que o gestor faz ao anexar é a mesma do app do WhatsApp, e não é
cosmética: ela decide se o arquivo viaja INTACTO ou se passa por conversão.

- **documento** → passthrough byte a byte. É o caminho que preserva o original
  (teto de 100 MB na Cloud API, sem recompressão nenhuma). Chega como arquivo
  na conversa, não como foto — o destinatário abre/baixa.
- **imagem** → chega como foto (com miniatura na conversa), mas a Cloud API só
  aceita **JPEG/PNG, 8-bit RGB ou RGBA, até 5 MB**. HEIC do iPhone, WebP, PNG
  de 16 bits e foto de 12 MP não passam por esse crivo — então a conversão
  acontece aqui, antes de subir, senão o envio falha no provedor com um erro
  que não diz nada ao gestor.

O que já está dentro das regras **não é reencodado**: recomprimir um JPEG
válido só perderia qualidade sem motivo. A conversão só entra quando o arquivo
não passaria.

NOTA sobre "HD": não existe parâmetro de qualidade/resolução na API (conferido
na referência oficial da Cloud API — o objeto de mídia aceita `id`/`link` e
legenda, mais nada). O que o app do WhatsApp chama de "HD" é ele próprio
reduzindo MENOS antes do upload. Por isso o teto de lado maior mora aqui, em
`LADO_MAIOR_PX`: oferecer a escolha de qualidade depois é trocar essa constante
por um parâmetro, não mexer no resto do caminho.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

log = logging.getLogger("hubcapture.anexo_whatsapp")

FORMATOS = ("documento", "imagem")

# ── Limites da Cloud API (pontos de calibração) ─────────────────────────────
# Fonte: referência oficial da Cloud API — "Images must be 8-bit, RGB or RGBA",
# JPEG/PNG até 5 MB; documento (PDF/Office) até 100 MB.
MAX_IMAGEM_BYTES = 5 * 1024 * 1024
MAX_DOCUMENTO_BYTES = 100 * 1024 * 1024
MIMES_IMAGEM = ("image/jpeg", "image/png")

# Teto de lado maior ao converter. 1600 px é o que se reporta como a qualidade
# "padrão" do app; o modo HD do app sobe para ~4096 px. Ver nota do módulo.
LADO_MAIOR_PX = 1600
QUALIDADE_JPEG = 85
QUALIDADE_MINIMA_JPEG = 60


class AnexoInvalido(Exception):
    """Anexo que não pode ser enviado no formato pedido (mensagem ao gestor)."""


@dataclass(frozen=True)
class Anexo:
    """Arquivo pronto para subir, já no formato escolhido."""

    conteudo: bytes
    nome: str
    mime: str
    formato: str
    convertido: bool = False

    @property
    def tamanho(self) -> int:
        return len(self.conteudo)


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f}MB"


def _pillow():
    """Import preguiçoso — como o resto dos providers opcionais do Hub."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:  # pragma: no cover - ambiente sem o extra instalado
        return None
    return Image


def _trocar_extensao(nome: str, ext: str) -> str:
    base = (nome or "anexo").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    raiz = base.rsplit(".", 1)[0] if "." in base else base
    return f"{raiz or 'anexo'}.{ext}"


def _serializar(img, tem_alfa: bool) -> tuple[bytes, str, str]:
    """Salva a imagem já normalizada, cabendo no teto de 5 MB.

    PNG preserva a transparência mas explode de tamanho em foto; JPEG é o
    inverso. Por isso o alfa decide o container, e o JPEG ainda tem a escada de
    qualidade/dimensão para caber no limite.
    """
    if tem_alfa:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        if buf.tell() <= MAX_IMAGEM_BYTES:
            return buf.getvalue(), "image/png", "png"
        # PNG estourou: achata sobre branco e segue como JPEG.
        from PIL import Image  # noqa: PLC0415

        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1])
        img = fundo

    qualidade = QUALIDADE_JPEG
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=qualidade, optimize=True, progressive=True)
        if buf.tell() <= MAX_IMAGEM_BYTES:
            return buf.getvalue(), "image/jpeg", "jpg"
        if qualidade > QUALIDADE_MINIMA_JPEG:
            qualidade -= 10
            continue
        # Qualidade no piso e ainda grande: reduz a dimensão.
        largura, altura = img.size
        if max(largura, altura) <= 320:
            raise AnexoInvalido(
                "IMAGEM_GRANDE_DEMAIS: não foi possível caber no limite de "
                f"{_mb(MAX_IMAGEM_BYTES)} do WhatsApp para foto — envie como documento "
                "para preservar o arquivo original."
            )
        img = img.resize((max(1, largura // 2), max(1, altura // 2)))
        qualidade = QUALIDADE_JPEG


def _converter(conteudo: bytes, nome: str) -> Anexo:
    Image = _pillow()
    if Image is None:
        raise AnexoInvalido(
            "IMAGEM_NAO_SUPORTADA: este arquivo precisa ser convertido para JPEG/PNG "
            "antes de virar foto no WhatsApp, e o processamento de imagem não está "
            "disponível no servidor — envie como documento."
        )
    try:
        img = Image.open(io.BytesIO(conteudo))
        img.load()
    except Exception as exc:  # pragma: no cover - arquivo corrompido/não-imagem
        raise AnexoInvalido(
            "ARQUIVO_NAO_E_IMAGEM: não consegui ler este arquivo como imagem — "
            "envie como documento."
        ) from exc

    tem_alfa = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    # A API exige 8-bit RGB/RGBA: modos exóticos (P, CMYK, I;16, L) viram um dos dois.
    img = img.convert("RGBA" if tem_alfa else "RGB")

    maior = max(img.size)
    if maior > LADO_MAIOR_PX:
        escala = LADO_MAIOR_PX / maior
        img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))))

    dados, mime, ext = _serializar(img, tem_alfa)
    return Anexo(
        conteudo=dados,
        nome=_trocar_extensao(nome, ext),
        mime=mime,
        formato="imagem",
        convertido=True,
    )


def preparar(conteudo: bytes, nome: str, mime: str | None, formato: str) -> Anexo:
    """Devolve o anexo pronto para o formato escolhido.

    `documento` nunca toca no conteúdo — é justamente o que o gestor escolhe
    quando quer o arquivo original do outro lado.
    """
    if formato not in FORMATOS:
        raise AnexoInvalido(f"FORMATO_INVALIDO: use {' ou '.join(FORMATOS)}")
    if not conteudo:
        raise AnexoInvalido("ARQUIVO_VAZIO")

    nome = (nome or "anexo").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    mime = (mime or "").split(";")[0].strip().lower() or "application/octet-stream"

    if formato == "documento":
        if len(conteudo) > MAX_DOCUMENTO_BYTES:
            raise AnexoInvalido(
                f"ARQUIVO_GRANDE_DEMAIS: o WhatsApp aceita até {_mb(MAX_DOCUMENTO_BYTES)} "
                "por documento."
            )
        return Anexo(conteudo=conteudo, nome=nome, mime=mime, formato="documento")

    # Já dentro das regras da API: sobe intacto (reencodar só perderia qualidade).
    if mime in MIMES_IMAGEM and len(conteudo) <= MAX_IMAGEM_BYTES:
        return Anexo(conteudo=conteudo, nome=nome, mime=mime, formato="imagem")

    return _converter(conteudo, nome)
