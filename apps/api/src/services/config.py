"""Configuração runtime — fonte de verdade das credenciais/URLs dos providers.

O painel admin grava aqui (via API); Firecrawl, LLM e os connectors consultam
`resolver(chave)` em runtime (DB), com fallback para o `.env`/Settings. Segredos
são cifrados em repouso (Fernet) e nunca retornados em claro na listagem.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..db.session import SessionLocal
from ..models.configuracao import Configuracao


# Catálogo de chaves configuráveis pelo painel. `default` vem do Settings (.env).
# `provider` agrupa as chaves por provider na UI (Firecrawl, Crawl4AI, LLM…);
# None = chave agrupada só pela categoria (fontes de dados, e-mail…).
def _c(
    chave: str,
    label: str,
    categoria: str,
    secreto: bool,
    provider: str | None = None,
) -> dict:
    return {
        "chave": chave,
        "label": label,
        "categoria": categoria,
        "secreto": secreto,
        "provider": provider,
    }


CATALOGO: list[dict] = [
    _c("firecrawl_api_key", "Firecrawl API Key", "scraping", True, "firecrawl"),
    _c("firecrawl_base_url", "Firecrawl base URL", "scraping", False, "firecrawl"),
    _c("crawl4ai_base_url", "Crawl4AI servidor URL (Docker)", "scraping", False, "crawl4ai"),
    _c("crawl4ai_api_token", "Crawl4AI API token", "scraping", True, "crawl4ai"),
    _c(
        "scraping_provider",
        "Scraper preferido (auto|crawl4ai|firecrawl)",
        "scraping",
        False,
        "scraping",
    ),
    _c("llm_api_key", "LLM API Key", "ia", True, "llm"),
    _c("llm_model_resumo", "Modelo LLM (resumo)", "ia", False, "llm"),
    _c("llm_model_chat", "Modelo LLM (chat)", "ia", False, "llm"),
    _c("embedding_api_key", "Embeddings API Key", "ia", True, "embeddings"),
    _c("embedding_model", "Modelo de embeddings", "ia", False, "embeddings"),
    _c("transferegov_ff_base_url", "TransfereGov FF base URL", "fonte", False),
    _c("transferegov_esp_base_url", "TransfereGov Especiais base URL", "fonte", False),
    _c(
        "transferegov_voluntarias_base_url",
        "TransfereGov Voluntárias base URL (api-publica)",
        "fonte",
        False,
    ),
    _c("transferegov_disc_csv_url", "TransfereGov Discricionárias CSV", "fonte", False),
    _c("fns_consulta_url", "FNS consulta URL", "fonte", False),
    _c("fnde_base_url", "FNDE base URL", "fonte", False),
    _c("serpro_base_url", "SERPRO base URL", "fonte", False),
    _c("serpro_token", "SERPRO token", "fonte", True),
    _c("serpro_painel_url", "SERPRO painel público (dd-publico, scraping)", "fonte", False),
    _c(
        "transferegov_noticias_url",
        "TransfereGov notícias RSS (painel informativo)",
        "fonte",
        False,
    ),
    _c("fpm_base_url", "FPM base URL", "fonte", False),
    _c("emendas_base_url", "Emendas base URL", "fonte", False),
    _c(
        "emendas_api_key",
        "Emendas — chave-api-dados (Portal da Transparência)",
        "fonte",
        True,
    ),
    _c("siconfi_csv_url", "Siconfi/CAUC CSV (Tesouro)", "fonte", False),
    _c("sismob_base_url", "SISMOB base URL (obras saúde)", "fonte", False),
    _c("simec_base_url", "SIMEC base URL (obras educação)", "fonte", False),
    _c("caixa_obras_base_url", "CAIXA/SIORB base URL (obras infra)", "fonte", False),
    _c("ibge_localidades_url", "IBGE Localidades base URL (busca de municípios)", "fonte", False),
    _c("uniq_api_key", "Uniq API Key (WhatsApp)", "whatsapp", True),
    _c("uniq_base_url", "Uniq base URL", "whatsapp", False),
    _c("uniq_webhook_token", "Uniq webhook token", "whatsapp", True),
    # E-mail transacional (SMTP) — recuperação de senha, convites, boas-vindas
    _c("email_smtp_host", "SMTP host", "email", False),
    _c("email_smtp_port", "SMTP porta (587 TLS / 465 SSL)", "email", False),
    _c("email_smtp_user", "SMTP usuário", "email", False),
    _c("email_smtp_password", "SMTP senha", "email", True),
    _c("email_from", "Remetente (From)", "email", False),
    _c("app_base_url", "URL pública do app (links de e-mail)", "email", False),
]
_CATALOGO_POR_CHAVE = {c["chave"]: c for c in CATALOGO}


def chave_valida(chave: str) -> bool:
    return chave in _CATALOGO_POR_CHAVE


def _fernet() -> Fernet:
    raw = settings.config_secret_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def _default(chave: str) -> str | None:
    val = getattr(settings, chave, None)
    return val or None


def _mascarar(valor: str) -> str:
    return "••••" + valor[-4:] if len(valor) >= 4 else "••••"


async def _row(session: AsyncSession, chave: str) -> Configuracao | None:
    return (
        await session.execute(select(Configuracao).where(Configuracao.chave == chave))
    ).scalar_one_or_none()


async def definir(session: AsyncSession, chave: str, valor: str | None) -> None:
    """Grava/atualiza uma chave conhecida. Cifra em repouso se for segredo."""
    meta = _CATALOGO_POR_CHAVE[chave]
    secreto = bool(meta["secreto"])
    cifrado = False
    valor_store = valor
    if secreto and valor:
        valor_store = _fernet().encrypt(valor.encode()).decode()
        cifrado = True
    stmt = (
        pg_insert(Configuracao)
        .values(
            chave=chave,
            valor=valor_store,
            secreto=secreto,
            cifrado=cifrado,
            categoria=meta["categoria"],
            descricao=meta.get("label"),
        )
        .on_conflict_do_update(
            index_elements=["chave"],
            set_={"valor": valor_store, "cifrado": cifrado, "secreto": secreto},
        )
    )
    await session.execute(stmt)


async def get_valor(session: AsyncSession, chave: str) -> str | None:
    """Valor efetivo (DB decifrado > default do .env)."""
    row = await _row(session, chave)
    if row is not None and row.valor is not None:
        if row.cifrado:
            return _fernet().decrypt(row.valor.encode()).decode()
        return row.valor
    return _default(chave)


async def listar_catalogo(session: AsyncSession) -> list[dict]:
    """Catálogo com status por chave (segredos mascarados, nunca em claro)."""
    rows = {r.chave: r for r in (await session.execute(select(Configuracao))).scalars().all()}
    saida: list[dict] = []
    for meta in CATALOGO:
        chave = meta["chave"]
        row = rows.get(chave)
        efetivo = await get_valor(session, chave)
        configurado = efetivo not in (None, "")
        if row and row.valor is not None:
            origem = "banco"  # gravado pelo painel
        elif configurado:
            origem = "env"  # fallback do .env/Settings
        else:
            origem = "padrao"  # nada definido
        item = {
            "chave": chave,
            "label": meta["label"],
            "categoria": meta["categoria"],
            "provider": meta.get("provider"),
            "secreto": meta["secreto"],
            "configurado": configurado,
            "origem": origem,
        }
        if meta["secreto"]:
            item["valor"] = _mascarar(efetivo) if configurado else None
        else:
            item["valor"] = efetivo
        saida.append(item)
    return saida


async def resolver(chave: str) -> str | None:
    """Acesso runtime (usado por Firecrawl/LLM/connectors). Abre sessão própria."""
    async with SessionLocal() as s:
        return await get_valor(s, chave)
