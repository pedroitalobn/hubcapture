"""Schemas do painel de configuração runtime (credenciais de provider)."""

from __future__ import annotations

from pydantic import BaseModel


class ConfigItem(BaseModel):
    chave: str
    label: str
    categoria: str
    provider: str | None = None  # agrupamento por provider na UI (firecrawl, llm…)
    secreto: bool
    configurado: bool
    origem: str  # 'banco' (painel) | 'env' (fallback .env) | 'padrao' (não definido)
    valor: str | None = None  # segredos vêm mascarados


class ConfigSet(BaseModel):
    chave: str
    valor: str | None = None


class LlmProviderOut(BaseModel):
    id: str
    label: str
    chave: str  # nome da chave no catálogo (llm_<id>_api_key)
    configurado: bool
    chave_mascarada: str | None = None
    docs_url: str
    modelo_chat: bool = False  # este provedor é o do modelo de chat atual
    modelo_resumo: bool = False


class LlmChaveIn(BaseModel):
    api_key: str


class LlmModelosOut(BaseModel):
    provider: str
    modelos: list[str]
    origem: str  # 'api' (listagem ao vivo) | 'fallback' (lista curada)
    erro: str | None = None


class ConhecimentoCreate(BaseModel):
    titulo: str
    conteudo: str
    categoria: str | None = None
    tags: list[str] | None = None


# ── Diagnóstico de fontes (admin) ──────────────────────────────────────────
class UltimaColeta(BaseModel):
    status: str | None = None  # 'ok' | 'degradado' | 'erro'
    registros: int | None = None
    finalizado_em: str | None = None
    erro: str | None = None


class FonteDiagnostico(BaseModel):
    fonte: str
    saudavel: bool  # health_check ao vivo (com timeout)
    ultima_coleta: UltimaColeta | None = None
    # PAUSA (painel admin): fonte pausada não entra nas rodadas de coleta.
    # `pausavel=False` = connector fora do catálogo de pausa — aparece no
    # diagnóstico, mas não tem toggle (não se pausa o que não se cadastrou).
    ativa: bool = True
    pausavel: bool = False
    label: str | None = None


class FonteToggle(BaseModel):
    """Payload do liga/desliga de uma fonte no painel admin."""

    fonte: str
    ativa: bool


class DiagnosticoFontes(BaseModel):
    """Estado real da ingestão: fontes ao vivo + providers de scraping/IA."""

    fontes: list[FonteDiagnostico] = []
    firecrawl_configurado: bool = False
    crawl4ai_configurado: bool = False
    llm_configurado: bool = False
    emendas_api_key_configurada: bool = False
