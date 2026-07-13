"""Cliente Uniq.chat (WhatsApp) — envio de mensagens (alertas + chat).

Credencial/URL vêm do painel admin (config runtime). Desabilitado sem
`uniq_api_key` (retorna False, sem erro) — o alerta ainda fica no painel.
"""

from __future__ import annotations

import httpx

from ..services import config as config_service

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def habilitado() -> bool:
    return bool(await config_service.resolver("uniq_api_key"))


async def enviar(telefone: str, mensagem: str) -> bool:
    """Envia uma mensagem WhatsApp. Retorna True se despachada, False se desabilitado."""
    api_key = await config_service.resolver("uniq_api_key")
    if not api_key:
        return False
    base = await config_service.resolver("uniq_base_url") or "https://api.uniq.chat"
    payload = {"phone": telefone, "message": mensagem}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT) as client:
        resp = await client.post("/v1/messages", json=payload, headers=headers)
        resp.raise_for_status()
    return True


async def validar_webhook(token: str | None) -> bool:
    """Confere o token do webhook de entrada (se configurado)."""
    esperado = await config_service.resolver("uniq_webhook_token")
    if not esperado:
        return True  # sem token configurado → não valida (dev)
    return token == esperado
