"""Agente do Dynamic Island: roteador fallback, executores sob RLS e eventos."""

from __future__ import annotations

from sqlalchemy import select, text

from src.ai import agent
from src.db.session import SessionLocal, rls_session
from src.models.usuario import Usuario
from src.services import modulos as modulos_service

from .conftest import _owner_engine


async def _ligar_modulo(chave: str) -> None:
    """Liga um módulo desativado por padrão (o teste declara o que precisa)."""
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO configuracoes (chave, valor, secreto, cifrado, categoria) "
                "VALUES (:c, 'on', false, false, 'modulos') "
                "ON CONFLICT (chave) DO UPDATE SET valor = 'on'"
            ),
            {"c": f"modulo_{chave}"},
        )
    modulos_service.limpar_cache()


def test_roteador_fallback_por_palavra_chave() -> None:
    assert agent.escolher_tool_fallback("quanto recebi de repasses?") == ("repasses_visao_geral")
    assert agent.escolher_tool_fallback("quais propostas vencem este mês?") == ("propostas_prazos")
    assert agent.escolher_tool_fallback("tem edital disponível?") == "propostas_listar"
    assert agent.escolher_tool_fallback("como está o CAUC?") == "conformidade_resumo"
    assert agent.escolher_tool_fallback("obras paralisadas?") == "obras_resumo"
    assert agent.escolher_tool_fallback("me dá as notícias") == "noticias_transferegov"
    assert agent.escolher_tool_fallback("bom dia") == "repasses_visao_geral"
    # novas ferramentas: minhas propostas, alertas, ações e apoio
    assert agent.escolher_tool_fallback("minhas propostas favoritas") == "minhas_propostas"
    assert agent.escolher_tool_fallback("favoritar a proposta 14275/2026") == ("favoritar_proposta")
    assert agent.escolher_tool_fallback("algum alerta de atualização?") == ("alertas_atualizacoes")
    assert agent.escolher_tool_fallback("roda uma varredura aí") == "alertas_varredura"
    assert agent.escolher_tool_fallback("emendas do parlamentar") == "emendas_resumo"
    assert agent.escolher_tool_fallback("quanto está empenhado?") == "captacao_resumo"
    assert agent.escolher_tool_fallback("o que é empenho?") == "class_buscar"
    assert agent.escolher_tool_fallback("qual o código IBGE de Mossoró?") == ("municipios_buscar")


def test_tools_no_formato_openai() -> None:
    tools = agent._tools_openai(agent.TOOLS)
    assert len(tools) == len(agent.TOOLS)
    for t in tools:
        assert t["type"] == "function"
        assert t["function"]["name"] in agent.TOOLS
        assert t["function"]["parameters"]["type"] == "object"


async def test_tools_ativas_respeita_modulos_desligados() -> None:
    """Com conformidade/obras/recebidos desativados (padrão do registro), o
    copiloto não expõe — nem executa — as ferramentas desses eixos."""
    async with SessionLocal() as s:
        tools = await agent.tools_ativas(s)
    assert "conformidade_resumo" not in tools and "obras_resumo" not in tools
    assert "repasses_visao_geral" not in tools and "emendas_resumo" not in tools
    # eixos ligados por padrão continuam disponíveis
    assert "propostas_listar" in tools and "minhas_propostas" in tools
    assert "noticias_transferegov" in tools and "contatos_buscar" in tools
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
    await _ligar_modulo("recebidos")
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

    u = await seed_user("islandprazo@x.com")
    await seed_municipio(u, "3550308")
    perto = (date.today() + timedelta(days=3)).isoformat()
    async with _owner_engine.begin() as conn:
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


async def test_minhas_propostas_e_favoritar_sob_rls(seed_user, seed_municipio) -> None:
    """A ferramenta de AÇÃO favorita a proposta achada pela busca e a leitura
    'minhas_propostas' devolve exatamente as favoritadas."""
    u = await seed_user("islandfav@x.com")
    await seed_municipio(u, "3550308")
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO propostas (fonte, id_externo, titulo, numero_proposta, "
                "municipio_ibge, cache_atualizado_em) VALUES "
                "('transferegov_ff','FAV1','UBS do Centro','14275/2026','3550308', now())"
            )
        )
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        vazio = await agent._executar_tool(s, usuario, "minhas_propostas", {})
        assert vazio["total"] == 0

        acao = await agent._executar_tool(
            s, usuario, "favoritar_proposta", {"consulta": "14275/2026"}
        )
        assert acao["ok"] is True and acao["favoritada"]["titulo"] == "UBS do Centro"

        minhas = await agent._executar_tool(s, usuario, "minhas_propostas", {})
        assert minhas["total"] == 1
        assert minhas["propostas"][0]["numero_proposta"] == "14275/2026"


async def test_alertas_listar_e_marcar_lidos(seed_user, seed_municipio) -> None:
    u = await seed_user("islandalerta@x.com")
    await seed_municipio(u, "3550308")
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alertas (usuario_id, tipo, payload, lido) VALUES "
                "(:u, 'nova_proposta', CAST(:p AS jsonb), false)"
            ),
            {"u": u, "p": '{"titulo": "Creche Norte", "municipio_ibge": "3550308"}'},
        )
    async with rls_session(u) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == u))).scalar_one()
        dado = await agent._executar_tool(s, usuario, "alertas_atualizacoes", {})
        assert dado["total"] == 1 and dado["alertas"][0]["titulo"] == "Creche Norte"

        marcados = await agent._executar_tool(s, usuario, "alertas_marcar_lidos", {})
        assert marcados["marcados"] == 1

        depois = await agent._executar_tool(s, usuario, "alertas_atualizacoes", {})
        assert depois["total"] == 0
