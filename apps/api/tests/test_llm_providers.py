"""Registry de provedores LLM: catálogo, parse de modelos e resolução p/ LiteLLM."""

from __future__ import annotations

import pytest

from src.services import config as config_service
from src.services import llm_providers


def test_todo_provider_tem_chave_no_catalogo() -> None:
    for p in llm_providers.PROVIDERS:
        assert config_service.chave_valida(llm_providers.chave_config(p.id))


def test_cobertura_dos_principais_providers() -> None:
    ids = {p.id for p in llm_providers.PROVIDERS}
    assert {"anthropic", "openai", "gemini", "kimi", "qwen", "grok", "deepseek", "glm"} <= ids


def test_parse_modelos_padrao_openai_filtra_nao_chat() -> None:
    p = llm_providers.POR_ID["openai"]
    payload = {
        "data": [
            {"id": "gpt-5"},
            {"id": "text-embedding-3-small"},
            {"id": "whisper-1"},
            {"id": "gpt-4o"},
        ]
    }
    modelos = [
        m for m in llm_providers._parse_modelos(p, payload) if llm_providers._e_modelo_chat(m)
    ]
    assert modelos == ["gpt-5", "gpt-4o"]


def test_parse_modelos_gemini_usa_generate_content() -> None:
    p = llm_providers.POR_ID["gemini"]
    payload = {
        "models": [
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
        ]
    }
    modelos = [
        m for m in llm_providers._parse_modelos(p, payload) if llm_providers._e_modelo_chat(m)
    ]
    assert modelos == ["gemini-2.5-pro"]


async def test_listar_modelos_cai_no_fallback_sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(provider, api_key):  # noqa: ANN001
        raise RuntimeError("sem rede")

    monkeypatch.setattr(llm_providers, "_fetch_modelos", _boom)
    out = await llm_providers.listar_modelos("anthropic", "sk-x")
    assert out["origem"] == "fallback"
    assert out["modelos"] == list(llm_providers.POR_ID["anthropic"].modelos_fallback)
    assert out["erro"]


def _mock_resolver(valores: dict[str, str | None]):
    async def _resolver(chave: str) -> str | None:
        return valores.get(chave)

    return _resolver


async def test_params_para_provider_prefixado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_providers.config_service,
        "resolver",
        _mock_resolver(
            {"llm_model_chat": "kimi/kimi-k2-turbo-preview", "llm_kimi_api_key": "mk-1"}
        ),
    )
    params = await llm_providers.params_para("llm_model_chat", "claude-sonnet-5")
    # kimi é OpenAI-compatible: prefixo openai/ + api_base do Moonshot
    assert params == {
        "model": "openai/kimi-k2-turbo-preview",
        "api_key": "mk-1",
        "api_base": "https://api.moonshot.ai/v1",
    }


async def test_params_para_provider_nativo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_providers.config_service,
        "resolver",
        _mock_resolver(
            {"llm_model_chat": "anthropic/claude-sonnet-5", "llm_anthropic_api_key": "sk-a"}
        ),
    )
    params = await llm_providers.params_para("llm_model_chat", "x")
    assert params == {"model": "anthropic/claude-sonnet-5", "api_key": "sk-a"}


async def test_params_para_legado_sem_prefixo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_providers.config_service,
        "resolver",
        _mock_resolver({"llm_model_chat": "claude-sonnet-5", "llm_api_key": "sk-leg"}),
    )
    params = await llm_providers.params_para("llm_model_chat", "x")
    assert params == {"model": "claude-sonnet-5", "api_key": "sk-leg"}


async def test_params_para_sem_credencial_desliga_ia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_providers.config_service, "resolver", _mock_resolver({}))
    assert await llm_providers.params_para("llm_model_chat", "claude-sonnet-5") is None
