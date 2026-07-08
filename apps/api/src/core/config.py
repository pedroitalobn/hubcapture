"""Configuração central (Pydantic Settings). Fonte única de verdade dos segredos/URLs.

Lê de variáveis de ambiente / .env. NUNCA commitar .env (ver .env.example na raiz).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Banco ────────────────────────────────────────────────────────────────
    # Runtime da API: role de app NÃO-superuser (RLS vale). É esta que o app usa.
    database_url: str = (
        "postgresql+asyncpg://hubcapture_app:app_secret@localhost:5432/hubcapture"
    )
    # Migrations/owner: role dona das tabelas. Só para Alembic; nunca no runtime.
    database_migrator_url: str = (
        "postgresql+asyncpg://hubcapture:postgres_secret@localhost:5432/hubcapture"
    )
    db_echo: bool = False

    # ── Auth / JWT ───────────────────────────────────────────────────────────
    jwt_secret: str = "troque-este-segredo-em-producao"
    jwt_refresh_secret: str = "troque-este-segredo-de-refresh"
    access_token_ttl: int = 900  # 15 min
    refresh_token_ttl: int = 1209600  # 14 dias

    # ── Cache-first ──────────────────────────────────────────────────────────
    cache_ttl_seconds: int = 21600  # 6h

    # ── Fontes ───────────────────────────────────────────────────────────────
    transferegov_ff_base_url: str = (
        "https://api.transferegov.gestao.gov.br/fundoafundo/"
    )
    # Recebidos (P1). URLs a calibrar contra as APIs/CSVs oficiais.
    fpm_base_url: str = "https://apidatalake.tesouro.gov.br/ords/transferencias/"
    emendas_base_url: str = "https://api.portaldatransparencia.gov.br/api-de-dados/"

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
