"""Anexo do WhatsApp: a escolha documento × imagem e o que ela faz com o arquivo.

O ponto que os testes travam: `documento` NUNCA toca no conteúdo (é o que o
gestor escolhe para preservar o original) e `imagem` só converte quando o
arquivo não passaria pelo crivo da Cloud API — JPEG válido e pequeno sobe
intacto, porque reencodar só perderia qualidade.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.notifications import uniq
from src.services import anexo_whatsapp
from src.services.anexo_whatsapp import AnexoInvalido, preparar


def _imagem(formato: str = "JPEG", tamanho=(800, 600), modo="RGB", **kwargs) -> bytes:
    buf = io.BytesIO()
    Image.new(modo, tamanho, (120, 180, 90) if modo != "RGBA" else (120, 180, 90, 128)).save(
        buf, format=formato, **kwargs
    )
    return buf.getvalue()


# ── documento: passthrough ──────────────────────────────────────────────────


def test_documento_nao_toca_no_conteudo() -> None:
    """O formato documento existe justamente para preservar o arquivo original."""
    bruto = _imagem("PNG", (3000, 2400))
    anexo = preparar(bruto, "obra.png", "image/png", "documento")
    assert anexo.conteudo == bruto
    assert anexo.formato == "documento"
    assert anexo.convertido is False
    assert anexo.mime == "image/png"


def test_documento_aceita_qualquer_tipo() -> None:
    anexo = preparar(b"%PDF-1.7 fake", "espelho.pdf", "application/pdf", "documento")
    assert anexo.mime == "application/pdf"
    assert anexo.conteudo == b"%PDF-1.7 fake"


def test_documento_respeita_teto_de_100mb() -> None:
    grande = b"x" * (anexo_whatsapp.MAX_DOCUMENTO_BYTES + 1)
    with pytest.raises(AnexoInvalido, match="ARQUIVO_GRANDE_DEMAIS"):
        preparar(grande, "grande.bin", "application/octet-stream", "documento")


# ── imagem: converte só quando precisa ──────────────────────────────────────


def test_imagem_valida_sobe_intacta() -> None:
    """JPEG dentro das regras não é reencodado — recomprimir perderia qualidade."""
    bruto = _imagem("JPEG", (800, 600))
    anexo = preparar(bruto, "foto.jpg", "image/jpeg", "imagem")
    assert anexo.conteudo == bruto
    assert anexo.convertido is False


def test_imagem_de_tipo_nao_aceito_e_convertida() -> None:
    """WebP/HEIC não passam no crivo da API (JPEG/PNG) — convertemos antes de subir."""
    bruto = _imagem("WEBP", (800, 600))
    anexo = preparar(bruto, "foto.webp", "image/webp", "imagem")
    assert anexo.convertido is True
    assert anexo.mime in anexo_whatsapp.MIMES_IMAGEM
    assert anexo.nome == "foto.jpg"
    assert Image.open(io.BytesIO(anexo.conteudo)).mode == "RGB"


def test_imagem_grande_e_reduzida_ao_teto_de_lado_maior() -> None:
    bruto = _imagem("WEBP", (5000, 2500))
    anexo = preparar(bruto, "panorama.webp", "image/webp", "imagem")
    assert max(Image.open(io.BytesIO(anexo.conteudo)).size) == anexo_whatsapp.LADO_MAIOR_PX
    assert anexo.tamanho <= anexo_whatsapp.MAX_IMAGEM_BYTES


def test_imagem_com_alfa_vira_rgba_valido() -> None:
    """A API exige 8-bit RGB ou RGBA: modo exótico tem que virar um dos dois."""
    bruto = _imagem("PNG", (400, 400), modo="RGBA")
    anexo = preparar(bruto, "logo.png", "image/webp", "imagem")
    assert Image.open(io.BytesIO(anexo.conteudo)).mode in ("RGB", "RGBA")


def test_imagem_modo_paleta_e_convertida() -> None:
    buf = io.BytesIO()
    Image.new("P", (300, 300)).save(buf, format="GIF")
    anexo = preparar(buf.getvalue(), "icone.gif", "image/gif", "imagem")
    assert anexo.convertido is True
    assert Image.open(io.BytesIO(anexo.conteudo)).mode in ("RGB", "RGBA")


def test_arquivo_que_nao_e_imagem_no_formato_imagem() -> None:
    with pytest.raises(AnexoInvalido, match="ARQUIVO_NAO_E_IMAGEM"):
        preparar(b"%PDF-1.7 fake", "espelho.pdf", "application/pdf", "imagem")


# ── contrato geral ──────────────────────────────────────────────────────────


def test_formato_invalido_e_arquivo_vazio() -> None:
    with pytest.raises(AnexoInvalido, match="FORMATO_INVALIDO"):
        preparar(b"x", "a.jpg", "image/jpeg", "hd")
    with pytest.raises(AnexoInvalido, match="ARQUIVO_VAZIO"):
        preparar(b"", "a.jpg", "image/jpeg", "imagem")


def test_nome_sem_caminho_e_mime_sem_parametros() -> None:
    anexo = preparar(b"conteudo", "/tmp/../foto.txt", "text/plain; charset=utf-8", "documento")
    assert anexo.nome == "foto.txt"
    assert anexo.mime == "text/plain"


# ── de-para para o `type` do WhatsApp ───────────────────────────────────────


def test_formato_vira_o_type_certo_da_api() -> None:
    """É essa chave que decide foto na conversa × arquivo para baixar."""
    assert uniq.TIPO_WHATSAPP["imagem"] == "image"
    assert uniq.TIPO_WHATSAPP["documento"] == "document"
    assert set(uniq.TIPO_WHATSAPP) == set(anexo_whatsapp.FORMATOS)


@pytest.mark.asyncio
async def test_enviar_midia_degrada_sem_credencial(monkeypatch) -> None:
    """Sem WhatsApp configurado o envio devolve False, como `enviar` — não explode."""
    monkeypatch.setattr(uniq.config_service, "resolver", lambda _chave: _none())
    anexo = preparar(b"conteudo", "a.pdf", "application/pdf", "documento")
    assert await uniq.enviar_midia("+5511988887777", anexo) is False


async def _none():
    return None
