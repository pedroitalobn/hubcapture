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
    database_url: str = "postgresql+asyncpg://hubcapture_app:app_secret@localhost:5432/hubcapture"
    # Migrations/owner: role dona das tabelas. Só para Alembic; nunca no runtime.
    database_migrator_url: str = (
        "postgresql+asyncpg://hubcapture:postgres_secret@localhost:5432/hubcapture"
    )
    db_echo: bool = False

    # ── Auth / JWT ───────────────────────────────────────────────────────────
    # ATENÇÃO: estes padrões são só para o dev local. Em produção o boot é
    # ABORTADO se continuarem (ver core/seguranca_boot.py) — quem lê o repo
    # conseguiria forjar token de qualquer usuário.
    jwt_secret: str = "troque-este-segredo-em-producao"
    jwt_refresh_secret: str = "troque-este-segredo-de-refresh"
    # válvula consciente p/ homologação atrás de domínio (mantém o aviso no log)
    permitir_segredo_padrao: bool = False
    access_token_ttl: int = 900  # 15 min
    refresh_token_ttl: int = 1209600  # 14 dias

    # ── Admin inicial (bootstrap no startup) ─────────────────────────────────
    # Se ambos preenchidos, a API cria/promove este superusuário ao subir, para
    # o primeiro login no painel admin. Vazio = não faz bootstrap.
    admin_email: str = ""
    admin_password: str = ""

    # ── Cache-first ──────────────────────────────────────────────────────────
    cache_ttl_seconds: int = 21600  # 6h

    # ── Fontes ───────────────────────────────────────────────────────────────
    transferegov_ff_base_url: str = "https://api.transferegov.gestao.gov.br/fundoafundo/"
    transferegov_ff_ibge_field: str = ""  # coluna IBGE; vazio = autodescoberta (OpenAPI)
    # Recebidos (P1). URLs a calibrar contra as APIs/CSVs oficiais.
    fpm_base_url: str = "https://apidatalake.tesouro.gov.br/ords/transferencias/"
    fpm_endpoint: str = ""  # rota no ORDS; vazio = autodescoberta (metadata-catalog)
    emendas_base_url: str = "https://api.portaldatransparencia.gov.br/api-de-dados/"
    emendas_api_key: str = ""  # chave-api-dados (Portal da Transparência) — obrigatória
    # Demais fontes (prontas para receber as APIs — calibrar rota/campos).
    # API pública do TransfereGov (docs por módulo em <base>/<modulo>/docs).
    transferegov_esp_base_url: str = "https://api-publica.transferegov.gestao.gov.br/especiais/"
    transferegov_esp_endpoint: str = ""  # vazio = autodescoberta (OpenAPI)
    transferegov_esp_ibge_field: str = ""
    transferegov_voluntarias_base_url: str = (
        "https://api-publica.transferegov.gestao.gov.br/voluntarias/"
    )
    transferegov_voluntarias_endpoint: str = ""  # vazio = autodescoberta (OpenAPI)
    transferegov_voluntarias_ibge_field: str = ""
    transferegov_disc_csv_url: str = "http://repositorio.dados.gov.br/seges/detru/"
    fns_consulta_url: str = "https://consultafns.saude.gov.br/"
    # Backend REST do ConsultaFNS (fonte primária; scraping segue como 2ª fonte)
    fns_api_url: str = "https://consultafns.saude.gov.br/recursos/"
    fns_api_endpoint: str = ""  # rota no backend; vazio = candidatos conhecidos
    fnde_base_url: str = "https://www.fnde.gov.br/sigefweb/"
    serpro_base_url: str = "https://gateway.apiserpro.serpro.gov.br/"
    # Painel público do SERPRO (Qlik, JS pesado) — extração via scraping headless.
    # Visão Geral do TransfereGov: dados ricos que a API pública não expõe;
    # coleta combinada = API primeiro, painel enriquece/faz fallback.
    serpro_painel_url: str = (
        "https://dd-publico.serpro.gov.br/extensions/painel/TransferegovbrVisaoGeral.html"
    )
    # Painel informativo — notícias oficiais (RSS do gov.br)
    transferegov_noticias_url: str = "https://www.gov.br/transferegov/pt-br/noticias/noticias/RSS"
    # Conformidade fiscal (CAUC/CAPAG) — CSV do Tesouro Transparente
    siconfi_csv_url: str = "https://www.tesourotransparente.gov.br/ckan/dataset/cauc/"
    # Obras (execução) — SISMOB (saúde), SIMEC (educação), CAIXA/SIORB (infra)
    sismob_base_url: str = "https://sismob.saude.gov.br/api/"
    simec_base_url: str = "https://simec.mec.gov.br/api/"
    caixa_obras_base_url: str = "https://webp.caixa.gov.br/siorb/api/"
    # IBGE Localidades — resolve nome do município → código IBGE (onboarding)
    ibge_localidades_url: str = "https://servicodados.ibge.gov.br/api/v1/localidades/"

    # ── E-mail transacional ────────────────────────────────────────────────
    app_base_url: str = "http://localhost:3000"  # base dos links de e-mail
    # Remetente (ex.: "Hub Capture <no-reply@hubcapture.com.br>"). Env EMAIL_FROM.
    email_from: str = ""
    # Maileroo (provedor de envio via API HTTP). Env MAILEROO_API_KEY. Se setado,
    # é o caminho preferido; senão cai no SMTP (config do painel admin).
    maileroo_api_key: str = ""
    maileroo_api_url: str = "https://smtp.maileroo.com/api/v2/emails"

    # ── Integrações de agenda de contatos (opcionais, painel admin) ─────────
    # OAuth de aplicação: sem client id/secret o provedor aparece indisponível.
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"  # 'common' aceita conta pessoal e corporativa
    # Apple/iCloud é CardDAV com senha de app — não precisa de credencial de app.
    apple_carddav_url: str = "https://contacts.icloud.com"

    # ── Scraping (Crawl4AI + Firecrawl) — coleta combinada / fallback ───────
    firecrawl_api_key: str = ""  # vazio = Firecrawl desabilitado
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    crawl4ai_base_url: str = ""  # URL do servidor Crawl4AI (Docker); vazio = desabilitado
    crawl4ai_api_token: str = ""  # token opcional do servidor Crawl4AI
    scraping_provider: str = "auto"  # auto | crawl4ai | firecrawl (preferência)

    @property
    def scraping_enabled(self) -> bool:
        return bool(self.firecrawl_api_key or self.crawl4ai_base_url)

    # ── IA (LiteLLM) — resumo/chat/embeddings (opcionais) ───────────────────
    llm_api_key: str = ""  # vazio = resumo/chat IA desabilitado
    llm_model_resumo: str = "claude-haiku-4-5-20251001"
    llm_model_chat: str = "claude-sonnet-5"
    embedding_api_key: str = ""  # vazio = embeddings/RAG desabilitado
    embedding_model: str = "text-embedding-3-small"  # dim 1536 (casa com o schema)

    # ── WhatsApp (Uniq.chat) — alertas + chat (opcional) ────────────────────
    uniq_api_key: str = ""  # vazio = WhatsApp desabilitado
    uniq_base_url: str = "https://api.uniq.chat"
    uniq_webhook_token: str = ""  # valida o webhook de entrada

    # ── Config runtime (painel admin) ───────────────────────────────────────
    # Chave para cifrar segredos em repouso na tabela `configuracoes` (Fernet).
    # Em produção defina um valor forte e estável; vazio usa jwt_secret (dev).
    config_secret_key: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
