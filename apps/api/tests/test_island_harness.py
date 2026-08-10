"""Harness próprio de tool calling: o loop do agente com bordas injetadas.

Nenhum teste aqui usa rede ou LLM real — o LLM é roteirizado e os executores
respondem dados canônicos (ai/harness.py). É o mesmo loop de produção."""

from __future__ import annotations

from src.ai import agent, harness


def test_catalogo_de_tools_integro() -> None:
    """Toda ferramenta tem descrição, JSON Schema válido, executor async,
    gatilhos e módulo conhecido — e a ordem de fallback cobre o catálogo."""
    assert harness.validar_tools() == []


def test_roteamento_golden() -> None:
    """A tabela de ouro do roteador sem-LLM roteia como o esperado."""
    assert harness.validar_roteamento() == []


def test_fatiar_preserva_o_texto() -> None:
    texto = "O município recebeu R$ 1.234,56 em 3 movimentações.\nPor fonte — fpm."
    assert "".join(agent._fatiar(texto)) == texto
    assert len(agent._fatiar(texto * 5)) > 1


async def test_loop_multi_rodada_com_llm_roteirizado() -> None:
    """Duas rodadas de tool calling e a resposta final, na ordem certa."""
    eventos = await harness.simular(
        "o que mudou nas minhas propostas?",
        roteiro=[
            harness.Turno(tool_calls=[("minhas_propostas", {})]),
            harness.Turno(tool_calls=[("alertas_atualizacoes", {"apenas_nao_lidos": True})]),
            harness.Turno(conteudo="Você acompanha 2 propostas; 1 alerta novo."),
        ],
        dados={
            "minhas_propostas": {"total": 2, "propostas": []},
            "alertas_atualizacoes": {"total": 1, "alertas": []},
        },
    )
    tools = [e["tool"] for e in eventos if "tool" in e]
    texto = "".join(e.get("delta", "") for e in eventos)
    assert tools == ["minhas_propostas", "alertas_atualizacoes"]
    assert texto == "Você acompanha 2 propostas; 1 alerta novo."


async def test_ferramenta_desconhecida_nao_derruba_o_loop() -> None:
    eventos = await harness.simular(
        "qualquer coisa",
        roteiro=[
            harness.Turno(tool_calls=[("nao_existe", {})]),
            harness.Turno(conteudo="segui em frente"),
        ],
    )
    assert "".join(e.get("delta", "") for e in eventos) == "segui em frente"


async def test_rodadas_esgotadas_respondem_em_streaming() -> None:
    """Estourando MAX_RODADAS, a resposta final vem por stream (vários deltas)."""
    roteiro = [
        harness.Turno(tool_calls=[("noticias_transferegov", {})]) for _ in range(agent.MAX_RODADAS)
    ]
    roteiro.append(harness.Turno(conteudo="resposta final depois de muitas rodadas"))
    eventos = await harness.simular(
        "notícias em loop",
        roteiro=roteiro,
        dados={"noticias_transferegov": {"noticias": []}},
    )
    deltas = [e["delta"] for e in eventos if "delta" in e]
    assert "".join(deltas) == "resposta final depois de muitas rodadas"
    assert len(deltas) > 1  # streaming real, não um bloco único
    assert len([e for e in eventos if "tool" in e]) == agent.MAX_RODADAS


async def test_territorio_e_injetado_como_padrao_das_tools() -> None:
    """O recorte do painel entra como `municipio` quando o LLM não pede outro."""
    capturados: list[tuple[str, dict]] = []

    async def _executor(nome: str, args: dict) -> dict:
        capturados.append((nome, args))
        return {"total": 0, "propostas": []}

    h = agent.Harness(
        llm=harness.LLMRoteirizado(
            [
                harness.Turno(tool_calls=[("propostas_listar", {})]),
                harness.Turno(conteudo="ok"),
            ]
        ),
        executor=_executor,
        tools=agent.TOOLS,
    )
    eventos = [
        e
        async for e in agent.executar(
            None, harness._UsuarioFake(), "propostas?", municipios=["3550308"], harness=h
        )
    ]
    assert capturados == [("propostas_listar", {"municipio": ["3550308"]})]
    assert "".join(e.get("delta", "") for e in eventos) == "ok"


async def test_fallback_sem_llm_formata_a_resposta() -> None:
    """Sem LLM: roteia por palavra-chave, executa e devolve texto legível."""
    eventos = await harness.simular(
        "quais propostas vencem este mês?",
        dados={"propostas_prazos": {"janela_dias": 30, "vencendo": []}},
    )
    assert eventos[0] == {"tool": "propostas_prazos"}
    assert "30 dias" in eventos[1]["delta"]


async def test_executor_com_erro_vira_payload_de_erro() -> None:
    """Executor que levanta exceção devolve {'erro': ...} e o loop responde."""

    async def _explode(_nome: str, _args: dict) -> dict:
        raise RuntimeError("fonte fora do ar")

    h = agent.Harness(
        llm=harness.LLMRoteirizado(
            [
                harness.Turno(tool_calls=[("noticias_transferegov", {})]),
                harness.Turno(conteudo="a fonte falhou, tente depois"),
            ]
        ),
        executor=_explode,
        tools=agent.TOOLS,
    )
    eventos = [
        e async for e in agent.executar(None, harness._UsuarioFake(), "notícias?", harness=h)
    ]
    assert "".join(e.get("delta", "") for e in eventos) == "a fonte falhou, tente depois"
