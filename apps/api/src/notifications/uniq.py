"""Cliente Uniq.chat (WhatsApp) — envio de mensagens e anexos (alertas + chat).

Credencial/URL vêm do painel admin (config runtime). Desabilitado sem
`uniq_api_key` (retorna False, sem erro) — o alerta ainda fica no painel.
"""

from __future__ import annotations

import base64

import httpx

from ..services import config as config_service
from ..services.anexo_whatsapp import Anexo

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# Anexo sobe um arquivo inteiro: 30s não cobre uma foto em rede ruim.
TIMEOUT_MIDIA = httpx.Timeout(120.0, connect=10.0)

# ── Rotas (pontos de calibração) ────────────────────────────────────────────
# O contrato de mídia do Uniq não é público; a rota é sobrescrevível pelo painel
# admin (`uniq_midia_endpoint`) para calibrar sem redeploy, como os connectors
# fazem com as rotas das fontes.
ROTA_MENSAGEM = "/v1/messages"
ROTA_MIDIA = "/v1/messages/media"

# De-para do formato do Hub para o `type` do WhatsApp. É essa chave que decide
# se o arquivo chega como FOTO na conversa ou como ARQUIVO para baixar.
TIPO_WHATSAPP = {"imagem": "image", "documento": "document"}


async def habilitado() -> bool:
    return bool(await config_service.resolver("uniq_api_key"))


async def _credenciais() -> tuple[str, str] | None:
    api_key = await config_service.resolver("uniq_api_key")
    if not api_key:
        return None
    base = await config_service.resolver("uniq_base_url") or "https://api.uniq.chat"
    return api_key, base


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def enviar(telefone: str, mensagem: str) -> bool:
    """Envia uma mensagem WhatsApp. Retorna True se despachada, False se desabilitado."""
    cred = await _credenciais()
    if cred is None:
        return False
    api_key, base = cred
    payload = {"phone": telefone, "message": mensagem}
    async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT) as client:
        resp = await client.post(ROTA_MENSAGEM, json=payload, headers=_headers(api_key))
        resp.raise_for_status()
    return True


async def enviar_midia(telefone: str, anexo: Anexo, legenda: str | None = None) -> bool:
    """Envia um anexo já preparado (ver `services/anexo_whatsapp.preparar`).

    O `anexo.formato` é o que o gestor escolheu ao anexar e vira o `type` da
    mensagem: `image` (foto na conversa) ou `document` (arquivo original).
    Retorna False quando o WhatsApp não está configurado — mesma degradação de
    `enviar`, para o fluxo de negócio não quebrar sem credencial.
    """
    cred = await _credenciais()
    if cred is None:
        return False
    api_key, base = cred
    rota = await config_service.resolver("uniq_midia_endpoint") or ROTA_MIDIA

    payload: dict = {
        "phone": telefone,
        "type": TIPO_WHATSAPP.get(anexo.formato, "document"),
        "media": {
            "filename": anexo.nome,
            "mime_type": anexo.mime,
            "data": base64.b64encode(anexo.conteudo).decode("ascii"),
        },
    }
    if legenda:
        payload["caption"] = legenda

    async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT_MIDIA) as client:
        resp = await client.post(rota, json=payload, headers=_headers(api_key))
        resp.raise_for_status()
    return True


async def validar_webhook(token: str | None) -> bool:
    """Confere o token do webhook de entrada (se configurado)."""
    esperado = await config_service.resolver("uniq_webhook_token")
    if not esperado:
        return True  # sem token configurado → não valida (dev)
    return token == esperado
