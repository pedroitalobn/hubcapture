"""Configuração runtime — fonte de verdade das credenciais/URLs dos providers.

O painel admin grava aqui (via API); Firecrawl, LLM e os connectors consultam
`resolver(chave)` em runtime (DB), com fallback para o `.env`/Settings. Segredos
são cifrados em repouso (Fernet) e nunca retornados em claro na listagem.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.crypto import cifrar, decifrar, mascarar
from ..db.session import SessionLocal
from ..models.configuracao import Configuracao


# Catálogo de chaves configuráveis pelo painel. `default` vem do Settings (.env).
def _c(chave: str, label: str, categoria: str, secreto: bool) -> dict:
    return {"chave": chave, "label": label, "categoria": categoria, "secreto": secreto}


CATALOGO: list[dict] = [
    _c("firecrawl_api_key", "Firecrawl API Key", "scraping", True),
    _c("firecrawl_base_url", "Firecrawl base URL", "scraping", False),
    _c("llm_api_key", "LLM API Key", "ia", True),
    _c("llm_model_resumo", "Modelo LLM (resumo)", "ia", False),
    _c("llm_model_chat", "Modelo LLM (chat)", "ia", False),
    _c("embedding_api_key", "Embeddings API Key", "ia", True),
    _c("embedding_model", "Modelo de embeddings", "ia", False),
    _c("transferegov_ff_base_url", "TransfereGov FF base URL", "fonte", False),
    _c("transferegov_esp_base_url", "TransfereGov Especiais base URL", "fonte", False),
    _c("transferegov_disc_csv_url", "TransfereGov Discricionárias CSV", "fonte", False),
    _c("fns_consulta_url", "FNS consulta URL", "fonte", False),
    _c("fnde_base_url", "FNDE base URL", "fonte", False),
    _c("serpro_base_url", "SERPRO base URL", "fonte", False),
    _c("serpro_token", "SERPRO token", "fonte", True),
    _c("fpm_base_url", "FPM base URL", "fonte", False),
    _c("emendas_base_url", "Emendas base URL", "fonte", False),
    _c("siconfi_csv_url", "Siconfi/CAUC CSV (Tesouro)", "fonte", False),
    _c("sismob_base_url", "SISMOB base URL (obras saúde)", "fonte", False),
    _c("simec_base_url", "SIMEC base URL (obras educação)", "fonte", False),
    _c("caixa_obras_base_url", "CAIXA/SIORB base URL (obras infra)", "fonte", False),
    # Agenda de contatos — OAuth de aplicação (Google/Microsoft) e CardDAV
    _c("google_client_id", "Google OAuth Client ID (contatos)", "integracoes", False),
    _c("google_client_secret", "Google OAuth Client Secret", "integracoes", True),
    _c("microsoft_client_id", "Microsoft OAuth Client ID (contatos)", "integracoes", False),
    _c("microsoft_client_secret", "Microsoft OAuth Client Secret", "integracoes", True),
    _c("microsoft_tenant", "Microsoft tenant (common/organizations/ID)", "integracoes", False),
    _c("apple_carddav_url", "Apple/iCloud CardDAV URL", "integracoes", False),
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


def _default(chave: str) -> str | None:
    val = getattr(settings, chave, None)
    return val or None


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
        valor_store = cifrar(valor)
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
            return decifrar(row.valor)
        return row.valor
    return _default(chave)


async def listar_catalogo(session: AsyncSession) -> list[dict]:
    """Catálogo com status por chave (segredos mascarados, nunca em claro)."""
    rows = {
        r.chave: r
        for r in (await session.execute(select(Configuracao))).scalars().all()
    }
    saida: list[dict] = []
    for meta in CATALOGO:
        chave = meta["chave"]
        row = rows.get(chave)
        efetivo = await get_valor(session, chave)
        configurado = efetivo not in (None, "")
        item = {
            "chave": chave,
            "label": meta["label"],
            "categoria": meta["categoria"],
            "secreto": meta["secreto"],
            "configurado": configurado,
            "origem": "banco" if row and row.valor is not None else "padrao",
        }
        if meta["secreto"]:
            item["valor"] = mascarar(efetivo) if configurado else None
        else:
            item["valor"] = efetivo
        saida.append(item)
    return saida


async def resolver(chave: str) -> str | None:
    """Acesso runtime (usado por Firecrawl/LLM/connectors). Abre sessão própria."""
    async with SessionLocal() as s:
        return await get_valor(s, chave)
