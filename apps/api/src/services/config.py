"""Configuração runtime — fonte de verdade das credenciais/URLs dos providers.

O painel admin grava aqui (via API); Firecrawl, LLM e os connectors consultam
`resolver(chave)` em runtime (DB), com fallback para o `.env`/Settings. Segredos
são cifrados em repouso (Fernet) e nunca retornados em claro na listagem.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.crypto import cifrar, decifrar, mascarar
from ..db.session import SessionLocal
from ..models.configuracao import Configuracao

log = logging.getLogger("hubcapture.config")


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
        "scraping_crawl4ai_local",
        "Crawl4AI local — biblioteca no próprio container (on|off)",
        "scraping",
        False,
        "crawl4ai_local",
    ),
    _c(
        "scraping_playwright",
        "Playwright local — Chromium headless no container (on|off)",
        "scraping",
        False,
        "playwright",
    ),
    _c(
        "scraping_provider",
        "Scraper preferido (auto|crawl4ai_local|playwright|crawl4ai|firecrawl)",
        "scraping",
        False,
        "scraping",
    ),
    _c("llm_api_key", "LLM API Key (genérica/legado)", "ia", True, "llm"),
    _c("llm_model_resumo", "Modelo LLM (resumo)", "ia", False, "llm"),
    _c("llm_model_chat", "Modelo LLM (chat)", "ia", False, "llm"),
    # Chaves por provedor de LLM (registry em services/llm_providers.py)
    _c("llm_anthropic_api_key", "Anthropic (Claude) API Key", "ia", True, "llm"),
    _c("llm_openai_api_key", "OpenAI (GPT) API Key", "ia", True, "llm"),
    _c("llm_gemini_api_key", "Google (Gemini) API Key", "ia", True, "llm"),
    _c("llm_deepseek_api_key", "DeepSeek API Key", "ia", True, "llm"),
    _c("llm_grok_api_key", "xAI (Grok) API Key", "ia", True, "llm"),
    _c("llm_kimi_api_key", "Moonshot (Kimi) API Key", "ia", True, "llm"),
    _c("llm_qwen_api_key", "Alibaba (Qwen) API Key", "ia", True, "llm"),
    _c("llm_glm_api_key", "Z.ai (GLM) API Key", "ia", True, "llm"),
    _c("embedding_api_key", "Embeddings API Key", "ia", True, "embeddings"),
    _c("embedding_model", "Modelo de embeddings", "ia", False, "embeddings"),
    _c("transferegov_ff_base_url", "TransfereGov FF base URL", "fonte", False),
    _c(
        "transferegov_ff_ibge_field",
        "TransfereGov FF coluna de IBGE (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    # Pareceres do plano de trabalho — pontos de calibração (§36). Sem estes,
    # o connector falha com mensagem clara em vez de devolver vazio silencioso.
    _c("pareceres_base_url", "Pareceres — base URL da API (se houver)", "fonte", False),
    _c("pareceres_endpoint", "Pareceres — rota da API", "fonte", False),
    _c(
        "pareceres_url_tramitacao",
        "Pareceres — URL da tela de tramitação ({plano} = nº do plano de trabalho)",
        "fonte",
        False,
    ),
    # Enriquecimento da proposta pelo módulo `especiais` (emenda + parlamentar
    # autor). A rota é DESCOBERTA no spec do módulo; estas chaves são o override
    # manual para quando a descoberta não bastar (§27).
    _c(
        "especiais_base_url",
        "TransfereGov Especiais — base da API pública (enriquecimento)",
        "fonte",
        False,
    ),
    _c(
        "emendas_esp_endpoint",
        "Emenda da proposta — rota no módulo especiais (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    _c(
        "planos_trabalho_esp_endpoint",
        "Plano de trabalho da proposta — rota no módulo especiais "
        "(padrão: planos_trabalho_especiais). É o elo que destrava os pareceres.",
        "fonte",
        False,
    ),
    _c(
        "planos_trabalho_esp_chave",
        "Plano de trabalho da proposta — parâmetro de filtro (padrão: id_proposta)",
        "fonte",
        False,
    ),
    _c(
        "empenhos_esp_endpoint",
        "Empenhos da proposta — rota no módulo especiais (padrão: empenhos_especiais)",
        "fonte",
        False,
    ),
    _c(
        "empenhos_esp_chave",
        "Empenhos da proposta — parâmetro de filtro (padrão: id_plano_acao, "
        "o único vínculo com a proposta que a rota aceita)",
        "fonte",
        False,
    ),
    _c(
        "emendas_esp_chave",
        "Emenda da proposta — parâmetro de filtro da rota (ex.: id_plano_acao)",
        "fonte",
        False,
    ),
    # Pacote de dados abertos do SIconv (ZIPs nacionais por tabela). A carga
    # diária de emendas (`jobs/siconv_diario`) baixa daqui; o nome de cada
    # arquivo é resolvido em runtime e estas chaves são o override manual.
    _c(
        "siconv_downloads_url",
        "SIconv — base dos downloads (ZIPs nacionais: emenda, proposta…)",
        "fonte",
        False,
    ),
    _c(
        "siconv_emenda_arquivo",
        "SIconv — nome do ZIP de emendas (vazio = tenta siconv_emenda.zip / emenda.zip)",
        "fonte",
        False,
    ),
    _c(
        "siconv_proposta_arquivo",
        "SIconv — nome do ZIP de propostas (vazio = tenta siconv_proposta.zip / proposta.zip)",
        "fonte",
        False,
    ),
    _c(
        "siconv_convenio_arquivo",
        "SIconv — nome do ZIP de convênios (vazio = tenta siconv_convenio.zip / convenio.zip)",
        "fonte",
        False,
    ),
    _c(
        "siconv_empenho_arquivo",
        "SIconv — nome do ZIP de empenhos (vazio = tenta siconv_empenho.zip / empenho.zip)",
        "fonte",
        False,
    ),
    _c(
        "siconv_propostas_escopo",
        "SIconv — escopo da carga de propostas: `territorio` (padrão, só os "
        "municípios monitorados) ou `nacional` (o país inteiro — milhões de linhas)",
        "fonte",
        False,
    ),
    _c("transferegov_esp_base_url", "TransfereGov Especiais base URL", "fonte", False),
    _c(
        "transferegov_esp_endpoint",
        "TransfereGov Especiais rota (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    _c(
        "transferegov_esp_ibge_field",
        "TransfereGov Especiais coluna de IBGE (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    _c(
        "transferegov_voluntarias_base_url",
        "TransfereGov Voluntárias base URL (api-publica)",
        "fonte",
        False,
    ),
    _c("transferegov_disc_csv_url", "TransfereGov Discricionárias CSV", "fonte", False),
    _c(
        "transferegov_voluntarias_endpoint",
        "TransfereGov Voluntárias rota (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    _c(
        "transferegov_voluntarias_ibge_field",
        "TransfereGov Voluntárias coluna de IBGE (autodescoberta se vazio)",
        "fonte",
        False,
    ),
    _c("fns_consulta_url", "FNS consulta URL (página, scraping)", "fonte", False),
    _c("fns_api_url", "FNS — API do ConsultaFNS (base URL)", "fonte", False),
    _c("fns_api_endpoint", "FNS — rota da API (autocalibração se vazio)", "fonte", False),
    _c("fnde_base_url", "FNDE base URL", "fonte", False),
    _c("dou_busca_url", "DOU — busca pública (in.gov.br)", "fonte", False),
    _c("dou_secao", "DOU — seção da conferência (do3 = contratos)", "fonte", False),
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
    _c("fpm_endpoint", "FPM rota no ORDS (autodescoberta se vazio)", "fonte", False),
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
    # Agenda de contatos — OAuth de aplicação (Google/Microsoft) e CardDAV (Apple)
    _c("google_client_id", "Google OAuth Client ID (contatos)", "integracoes", False, "google"),
    _c("google_client_secret", "Google OAuth Client Secret", "integracoes", True, "google"),
    _c(
        "microsoft_client_id",
        "Microsoft OAuth Client ID (contatos)",
        "integracoes",
        False,
        "microsoft",
    ),
    _c(
        "microsoft_client_secret",
        "Microsoft OAuth Client Secret",
        "integracoes",
        True,
        "microsoft",
    ),
    _c(
        "microsoft_tenant",
        "Microsoft tenant (common/organizations/ID)",
        "integracoes",
        False,
        "microsoft",
    ),
    _c("apple_carddav_url", "Apple/iCloud CardDAV URL", "integracoes", False, "apple"),
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
    # Plataforma — aparência do app. A flag permite portar a UI v2 → v1 sem
    # deploy: o web lê a versão ativa em GET /ui (público) e aplica `data-ui`.
    _c("ui_versao", "Versão da UI do app (v2 atual · v1 clássica)", "plataforma", False),
    # Acesso demo (apresentação/vendas) — sandbox com dados reais do cache.
    _c(
        "demo_ativo",
        "Acesso demo — botão 'Ver demonstração' no login (on|off)",
        "plataforma",
        False,
    ),
    _c(
        "demo_ibges",
        "Acesso demo — territorio da conta demo (códigos IBGE separados por vírgula; "
        "vazio = municípios com mais propostas no cache)",
        "plataforma",
        False,
    ),
    _c(
        "demo_video_url",
        "Acesso demo — vídeo dos artigos iniciais do Class (YouTube/Vimeo/mp4)",
        "plataforma",
        False,
    ),
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
            item["valor"] = mascarar(efetivo) if configurado else None
        else:
            item["valor"] = efetivo
        saida.append(item)
    return saida


async def resolver(chave: str) -> str | None:
    """Acesso runtime (usado por scrapers/LLM/connectors). Abre sessão própria.

    Banco fora do ar não pode derrubar a ingestão: o painel apenas SOBRESCREVE o
    `.env`, então sem banco vale o default do `.env` — o mesmo valor que valeria
    se ninguém tivesse configurado nada no painel. É também o que permite rodar
    o probe de fontes (`python -m src.tools.probe_fontes`) sem subir o Postgres.
    """
    try:
        async with SessionLocal() as s:
            return await get_valor(s, chave)
    except Exception:
        log.warning("configuração %r: banco indisponível, usando default do .env", chave)
        return _default(chave)
