"""Config runtime: set/get, cifra de segredos, máscara e resolver."""

from __future__ import annotations

from sqlalchemy import select

from src.db.session import SessionLocal
from src.models.configuracao import Configuracao
from src.services import config as service


async def test_definir_segredo_cifra_e_resolve() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, "firecrawl_api_key", "fc-super-secreta-1234")
        # valor em repouso está cifrado (não é o texto puro)
        async with s.begin():
            row = (
                await s.execute(
                    select(Configuracao).where(Configuracao.chave == "firecrawl_api_key")
                )
            ).scalar_one()
            assert row.cifrado is True
            assert row.valor != "fc-super-secreta-1234"
            # get_valor devolve decifrado
            assert await service.get_valor(s, "firecrawl_api_key") == "fc-super-secreta-1234"


async def test_listar_catalogo_mascara_segredos() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, "firecrawl_api_key", "abcd1234efgh5678")
            await service.definir(s, "fnde_base_url", "https://exemplo.fnde/")
        async with s.begin():
            itens = {i["chave"]: i for i in await service.listar_catalogo(s)}
        fc = itens["firecrawl_api_key"]
        assert fc["secreto"] is True and fc["configurado"] is True
        assert fc["valor"].startswith("••••") and "5678" in fc["valor"]
        assert "abcd1234" not in fc["valor"]  # nunca em claro
        # não-segredo mostra valor efetivo
        assert itens["fnde_base_url"]["valor"] == "https://exemplo.fnde/"


async def test_resolver_fallback_para_default_do_env() -> None:
    async with SessionLocal() as s:
        # sem override no banco → cai no default do Settings
        assert (await service.get_valor(s, "fpm_base_url")).startswith("http")
        # segredo sem valor → None
        assert await service.get_valor(s, "llm_api_key") in (None, "")


async def test_chave_desconhecida_rejeitada() -> None:
    assert service.chave_valida("firecrawl_api_key") is True
    assert service.chave_valida("chave_inexistente") is False


async def test_catalogo_agrupa_por_provider_e_expoe_origem() -> None:
    """Providers de scraping/IA são grupos próprios; origem distingue painel × .env."""
    async with SessionLocal() as s:
        async with s.begin():
            await service.definir(s, "crawl4ai_base_url", "http://crawl4ai:11235")
        async with s.begin():
            itens = {i["chave"]: i for i in await service.listar_catalogo(s)}

    assert itens["firecrawl_api_key"]["provider"] == "firecrawl"
    assert itens["crawl4ai_base_url"]["provider"] == "crawl4ai"
    assert itens["llm_api_key"]["provider"] == "llm"
    assert itens["embedding_model"]["provider"] == "embeddings"
    # chaves de fonte não têm provider (agrupam pela categoria)
    assert itens["fnde_base_url"]["provider"] is None

    # gravado pelo painel → origem 'banco'
    assert itens["crawl4ai_base_url"]["origem"] == "banco"
    # sem valor no banco mas com default do Settings/.env → origem 'env'
    assert itens["firecrawl_base_url"]["origem"] == "env"
    # sem valor em lugar nenhum → 'padrao' e não-configurado
    assert itens["llm_api_key"]["origem"] == "padrao"
    assert itens["llm_api_key"]["configurado"] is False
