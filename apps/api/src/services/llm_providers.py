"""Registry de provedores de LLM — cobertura das principais LLMs atuais.

Cada provedor tem sua própria API key no painel (`llm_<id>_api_key`). Ao plugar
a chave, os modelos daquele provedor são listados AO VIVO (endpoint /models da
própria fonte) — com fallback para uma lista curada se a chamada falhar. Os
modelos escolhidos são gravados como `<provider>/<modelo>` em `llm_model_chat`
e `llm_model_resumo`; `params_para()` resolve isso para os parâmetros do
LiteLLM (model prefixado + api_key + api_base quando OpenAI-compatible).

Compat: valor sem prefixo de provedor conhecido segue o caminho legado
(`llm_api_key` + modelo como está).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from . import config as config_service

TIMEOUT = httpx.Timeout(15.0, connect=10.0)


@dataclass(frozen=True)
class LlmProvider:
    id: str
    label: str
    litellm_prefix: str  # prefixo nativo do LiteLLM ("openai" p/ compatíveis)
    api_base: str | None  # base OpenAI-compatible (None = rota nativa)
    modelos_url: str  # endpoint de listagem de modelos do provedor
    auth: str  # 'bearer' | 'x-api-key' | 'query_key'
    modelos_fallback: tuple[str, ...]  # lista curada se a listagem falhar
    docs_url: str  # onde obter a API key (menos fricção no onboarding)


PROVIDERS: tuple[LlmProvider, ...] = (
    LlmProvider(
        id="anthropic",
        label="Anthropic (Claude)",
        litellm_prefix="anthropic",
        api_base=None,
        modelos_url="https://api.anthropic.com/v1/models",
        auth="x-api-key",
        modelos_fallback=(
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5",
        ),
        docs_url="https://console.anthropic.com/settings/keys",
    ),
    LlmProvider(
        id="openai",
        label="OpenAI (GPT)",
        litellm_prefix="openai",
        api_base=None,
        modelos_url="https://api.openai.com/v1/models",
        auth="bearer",
        modelos_fallback=("gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4o"),
        docs_url="https://platform.openai.com/api-keys",
    ),
    LlmProvider(
        id="gemini",
        label="Google (Gemini)",
        litellm_prefix="gemini",
        api_base=None,
        modelos_url="https://generativelanguage.googleapis.com/v1beta/models",
        auth="query_key",
        modelos_fallback=(
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ),
        docs_url="https://aistudio.google.com/apikey",
    ),
    LlmProvider(
        id="deepseek",
        label="DeepSeek",
        litellm_prefix="deepseek",
        api_base=None,
        modelos_url="https://api.deepseek.com/models",
        auth="bearer",
        modelos_fallback=("deepseek-chat", "deepseek-reasoner"),
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    LlmProvider(
        id="grok",
        label="xAI (Grok)",
        litellm_prefix="xai",
        api_base=None,
        modelos_url="https://api.x.ai/v1/models",
        auth="bearer",
        modelos_fallback=("grok-4", "grok-4-fast", "grok-3", "grok-3-mini"),
        docs_url="https://console.x.ai/",
    ),
    LlmProvider(
        id="kimi",
        label="Moonshot (Kimi)",
        litellm_prefix="openai",
        api_base="https://api.moonshot.ai/v1",
        modelos_url="https://api.moonshot.ai/v1/models",
        auth="bearer",
        modelos_fallback=("kimi-k2-turbo-preview", "kimi-k2-0905-preview"),
        docs_url="https://platform.moonshot.ai/console/api-keys",
    ),
    LlmProvider(
        id="qwen",
        label="Alibaba (Qwen)",
        litellm_prefix="openai",
        api_base="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        modelos_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models",
        auth="bearer",
        modelos_fallback=("qwen3-max", "qwen-plus", "qwen-turbo", "qwen-flash"),
        docs_url="https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
    ),
    LlmProvider(
        id="glm",
        label="Z.ai (GLM)",
        litellm_prefix="openai",
        api_base="https://api.z.ai/api/paas/v4",
        modelos_url="https://api.z.ai/api/paas/v4/models",
        auth="bearer",
        modelos_fallback=("glm-4.6", "glm-4.5", "glm-4.5-air", "glm-4.5-flash"),
        docs_url="https://z.ai/manage-apikey/apikey-list",
    ),
)
POR_ID: dict[str, LlmProvider] = {p.id: p for p in PROVIDERS}

# ids de modelo que não são de chat (listagens como a da OpenAI misturam tudo)
_EXCLUIR_TOKENS = (
    "embedding",
    "whisper",
    "tts",
    "audio",
    "realtime",
    "moderation",
    "dall-e",
    "davinci",
    "babbage",
    "image",
    "transcribe",
    "imagen",
    "veo",
    "aqa",
    "computer-use",
)


def chave_config(provider_id: str) -> str:
    """Nome da chave no catálogo de config: llm_<provider>_api_key."""
    return f"llm_{provider_id}_api_key"


def provider_valido(provider_id: str) -> bool:
    return provider_id in POR_ID


def _e_modelo_chat(model_id: str) -> bool:
    low = model_id.lower()
    return not any(t in low for t in _EXCLUIR_TOKENS)


def _parse_modelos(provider: LlmProvider, payload: dict) -> list[str]:
    if provider.id == "gemini":
        # {"models": [{"name": "models/gemini-...", "supportedGenerationMethods": [...]}]}
        modelos = []
        for m in payload.get("models", []):
            metodos = m.get("supportedGenerationMethods", [])
            if metodos and "generateContent" not in metodos:
                continue
            nome = str(m.get("name", "")).removeprefix("models/")
            if nome:
                modelos.append(nome)
        return modelos
    # padrão OpenAI/Anthropic: {"data": [{"id": ...}]}
    return [str(m["id"]) for m in payload.get("data", []) if m.get("id")]


async def _fetch_modelos(provider: LlmProvider, api_key: str) -> list[str]:
    headers = {"Accept": "application/json"}
    params: dict[str, str] = {}
    if provider.auth == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider.auth == "x-api-key":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif provider.auth == "query_key":
        params["key"] = api_key
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(provider.modelos_url, headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()
    modelos = [m for m in _parse_modelos(provider, payload) if _e_modelo_chat(m)]
    return sorted(set(modelos), reverse=True)  # mais novos primeiro (ids datados)


async def listar_modelos(provider_id: str, api_key: str) -> dict:
    """Modelos do provedor AO VIVO; cai na lista curada se a chamada falhar."""
    provider = POR_ID[provider_id]
    try:
        modelos = await _fetch_modelos(provider, api_key)
        if not modelos:
            raise ValueError("listagem vazia")
        return {"provider": provider_id, "modelos": modelos, "origem": "api", "erro": None}
    except Exception as exc:  # rede/chave inválida → fallback curado, nunca 500
        return {
            "provider": provider_id,
            "modelos": list(provider.modelos_fallback),
            "origem": "fallback",
            "erro": str(exc)[:200],
        }


async def params_para(chave_modelo: str, modelo_default: str) -> dict | None:
    """Parâmetros p/ litellm.acompletion a partir da config runtime.

    `chave_modelo` é 'llm_model_chat' ou 'llm_model_resumo'. Valor no formato
    '<provider>/<modelo>' usa a chave daquele provedor; sem prefixo conhecido,
    caminho legado (llm_api_key). Retorna None se não há credencial (IA off).
    """
    valor = await config_service.resolver(chave_modelo) or modelo_default
    provider_id, _, modelo = valor.partition("/")
    if modelo and provider_id in POR_ID:
        provider = POR_ID[provider_id]
        api_key = await config_service.resolver(chave_config(provider_id))
        if not api_key:  # chave do provedor removida → tenta a genérica
            api_key = await config_service.resolver("llm_api_key")
        if not api_key:
            return None
        params: dict = {"model": f"{provider.litellm_prefix}/{modelo}", "api_key": api_key}
        if provider.api_base:
            params["api_base"] = provider.api_base
        return params
    api_key = await config_service.resolver("llm_api_key")
    if not api_key:
        return None
    return {"model": valor, "api_key": api_key}
