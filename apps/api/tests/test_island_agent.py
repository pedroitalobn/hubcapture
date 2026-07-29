"""Agente do Dynamic Island: roteador fallback, executores sob RLS e eventos."""

from __future__ import annotations

from sqlalchemy import select

from src.ai import agent
from src.db.session import SessionLocal, rls_session
from src.models.usuario import Usuario


def test_roteador_fallback_por_palavra_chave() -> None:
    assert agent.escolher_tool_fallback("quanto recebi de repasses?") == ("repasses_visao_geral")
    assert agent.escolher_tool_fallback("quais propostas vencem este mês?") == ("propostas_prazos")
    assert agent.escolher_tool_fallback("tem edital disponível?") == "propostas_listar"
    assert agent.escolher_tool_fallback("como está o CAUC?") == "conformidade_resumo"
    assert agent.escolher_tool_fallback("obras paralisadas?") == "obras_resumo"
    assert agent.escolher_tool_fallback("me dá as notícias") == "noticias_transferegov"
    assert agent.escolher_tool_fallback("bom dia") == "repasses_visao_geral"


def test_tools_no_formato_openai() -> None:
    tools = agent._tools_openai(agent.TOOLS)
    assert len(tools) == len(agent.TOOLS)
    for t in tools:
        assert t["type"] == "function"
        assert t["function"]["name"] in agent.TOOLS
        assert t["function"]["parameters"]["type"] == "object"


async def test_tools_ativas_respeita_modulos_desligados() -> None:
    """Com conformidade/obras desativados (padrão), o copiloto não expõe — nem
    executa — as ferramentas desses eixos."""
    async with SessionLocal() as s:
        tools = await agent.tools_ativas(s)
    assert "conformidade_resumo" not in tools and "obras_resumo" not in tools
    assert "repasses_visao_geral" in tools and "noticias_transferegov" in tools
    # o roteador de fallback também só considera as ativas
    assert agent.escolher_tool_fallback("obras paralisadas?", tools) != "obras_resumo"


async def test_executar_tool_recusa_modulo_desligado(seed_user, seed_municipio) -> None:
    u = await seed_user("islandmod@x.com")
    await seed_municipio(u, "3550308")
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        erro = await agent._executar_tool(s, usuario, "obras_resumo", {})
    assert erro["erro"] == "MODULO_DESATIVADO: obras"


async def test_executar_fallback_repasses_sob_rls(seed_user, seed_municipio, seed_repasse) -> None:
    """Sem LLM key: o agente roteia p/ repasses e responde com o dado do
    território — e SÓ do território (RLS)."""
    u = await seed_user("island@x.com")
    await seed_municipio(u, "3550308")
    await seed_repasse("fpm", "R1", "3550308", valor="1000")
    await seed_repasse("fpm", "R2", "9999999", valor="777777")  # fora do território

    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        eventos = [e async for e in agent.executar(s, usuario, "quanto recebi?")]

    tools = [e["tool"] for e in eventos if "tool" in e]
    texto = "".join(e.get("delta", "") for e in eventos)
    assert tools == ["repasses_visao_geral"]
    assert "1.000,00" in texto
    assert "777" not in texto  # o repasse de outro município não vaza


async def test_executor_prazos(seed_user, seed_municipio) -> None:
    from datetime import date, timedelta

    from .conftest import _owner_engine

    u = await seed_user("islandprazo@x.com")
    await seed_municipio(u, "3550308")
    perto = (date.today() + timedelta(days=3)).isoformat()
    async with _owner_engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, municipio_ibge, "
                "prazos, cache_atualizado_em) VALUES ('transferegov_ff','PZ','Obra X',"
                "'3550308', CAST(:p AS jsonb), now())"
            ),
            {"p": f'[{{"tipo": "envio", "data_limite": "{perto}"}}]'},
        )
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        dado = await agent._executar_tool(s, usuario, "propostas_prazos", {"dias": 30})
        assert dado["vencendo"][0]["titulo"] == "Obra X"

        # ferramenta desconhecida não explode
        erro = await agent._executar_tool(s, usuario, "nao_existe", {})
        assert "erro" in erro
