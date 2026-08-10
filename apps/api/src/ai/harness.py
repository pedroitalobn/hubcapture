"""Harness PRÓPRIO de tool calling do Copiloto.

Exercita o loop do agente (ai/agent.py) de ponta a ponta SEM rede e SEM banco:
um LLM roteirizado devolve tool_calls prescritos e um executor fake responde
com dados canônicos. É o MESMO caminho de código da produção — só as bordas
(LLM/executores/catálogo) entram via `agent.Harness`.

Usos:
- testes (tests/test_island_harness.py);
- CLI de validação: python -m src.tools.harness_copiloto
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import agent


@dataclass
class Turno:
    """Um turno roteirizado do LLM: ou chama ferramentas, ou responde texto."""

    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    conteudo: str = ""


class LLMRoteirizado:
    """Substitui litellm.acompletion: devolve os turnos do roteiro em ordem.

    Suporta `stream=True` (fatiando o conteúdo do turno) para exercitar o
    caminho de rodadas esgotadas. Guarda `chamadas` para asserções."""

    def __init__(self, roteiro: list[Turno]):
        self._roteiro = list(roteiro)
        self.chamadas: list[dict] = []

    def _proximo(self) -> Turno:
        if not self._roteiro:
            return Turno(conteudo="(roteiro esgotado)")
        return self._roteiro.pop(0)

    async def __call__(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        turno = self._proximo()
        if kwargs.get("stream"):

            async def _stream():
                for i in range(0, len(turno.conteudo), 12):
                    yield {"choices": [{"delta": {"content": turno.conteudo[i : i + 12]}}]}

            return _stream()
        tool_calls = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": nome, "arguments": json.dumps(args)},
            }
            for i, (nome, args) in enumerate(turno.tool_calls)
        ]
        return {
            "choices": [
                {
                    "message": {
                        "content": turno.conteudo or None,
                        "tool_calls": tool_calls or None,
                    }
                }
            ]
        }


def executor_de(dados: dict[str, dict]):
    """Executor fake: responde cada ferramenta com o dado canônico do dicionário."""

    async def _exec(nome: str, _args: dict) -> dict:
        if nome not in dados:
            return {"erro": f"sem dado fake para {nome}"}
        return dados[nome]

    return _exec


class _UsuarioFake:
    papel = "executivo"
    id = None


async def simular(
    pergunta: str,
    roteiro: list[Turno] | None = None,
    dados: dict[str, dict] | None = None,
    *,
    tools: dict[str, dict[str, Any]] | None = None,
    municipios: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Roda o agente inteiro com as bordas fake e devolve a lista de eventos.

    `roteiro=None` exercita o caminho SEM LLM (roteador de fallback) — ainda
    sem banco, porque o executor fake responde as ferramentas."""
    h = agent.Harness(
        llm=LLMRoteirizado(roteiro) if roteiro is not None else None,
        executor=executor_de(dados or {}),
        tools=tools if tools is not None else agent.TOOLS,
    )
    if roteiro is None:
        # sem LLM de verdade E sem roteiro: força o caminho de fallback
        # (params_para pode achar chave no ambiente — o harness não quer rede)
        eventos: list[dict[str, Any]] = []
        nome = agent.escolher_tool_fallback(pergunta, h.tools)
        if nome is None:
            return [{"delta": "Nenhum módulo de dados está ativo na plataforma no momento."}]
        dado = await agent._executar_tool(
            None, _UsuarioFake(), nome, {}, territorio=municipios or [], tools=h.tools, harness=h
        )
        eventos.append({"tool": nome})
        eventos.append({"delta": agent._formatar_fallback(nome, dado)})
        return eventos
    return [
        e
        async for e in agent.executar(
            None, _UsuarioFake(), pergunta, municipios=municipios, harness=h
        )
    ]


# ── validações estruturais (CLI e testes) ───────────────────────────────────
def validar_tools() -> list[str]:
    """Confere o catálogo TOOLS: schema, executor, gatilhos. Vazio = ok."""
    problemas: list[str] = []
    import inspect

    for nome, t in agent.TOOLS.items():
        if not str(t.get("descricao") or "").strip():
            problemas.append(f"{nome}: sem descrição")
        params = t.get("parametros") or {}
        if params.get("type") != "object" or "properties" not in params:
            problemas.append(f"{nome}: parametros não é um JSON Schema de objeto")
        for req in params.get("required") or []:
            if req not in (params.get("properties") or {}):
                problemas.append(f"{nome}: required '{req}' fora de properties")
        if not inspect.iscoroutinefunction(t.get("executor")):
            problemas.append(f"{nome}: executor não é async")
        if not t.get("gatilhos"):
            problemas.append(f"{nome}: sem gatilhos de fallback")
        modulo = t.get("modulo")
        if modulo is not None and not agent.modulos_service.modulo_valido(modulo):
            problemas.append(f"{nome}: módulo desconhecido '{modulo}'")
    for nome in agent._PRIORIDADE_FALLBACK:
        if nome not in agent.TOOLS:
            problemas.append(f"_PRIORIDADE_FALLBACK cita ferramenta inexistente: {nome}")
    faltando = set(agent.TOOLS) - set(agent._PRIORIDADE_FALLBACK)
    if faltando:
        problemas.append(f"fora de _PRIORIDADE_FALLBACK: {sorted(faltando)}")
    return problemas


# perguntas de ouro do roteador sem-LLM (CLI e testes)
GOLDEN_ROTEAMENTO: list[tuple[str, str]] = [
    ("quanto recebi de repasses?", "repasses_visao_geral"),
    ("quais propostas vencem este mês?", "propostas_prazos"),
    ("tem edital disponível?", "propostas_listar"),
    ("como está o CAUC?", "conformidade_resumo"),
    ("obras paralisadas?", "obras_resumo"),
    ("me dá as notícias", "noticias_transferegov"),
    ("mostra minhas propostas favoritas", "minhas_propostas"),
    ("favoritar a proposta 14275/2026", "favoritar_proposta"),
    ("o que mudou? tem alerta novo?", "alertas_atualizacoes"),
    ("roda uma varredura de novidades", "alertas_varredura"),
    ("marcar como lidos os alertas", "alertas_marcar_lidos"),
    ("qual o parecer do plano de trabalho?", "pareceres_plano"),
    ("emendas do deputado?", "emendas_resumo"),
    ("o que estou monitorando?", "monitoramentos_listar"),
    ("minhas pastas", "pastas_listar"),
    ("telefone da secretaria de saúde", "contatos_buscar"),
    ("qual o código IBGE de Mossoró?", "municipios_buscar"),
    ("quanto está empenhado?", "captacao_resumo"),
    ("me dá um panorama do território", "perfil_visao_geral"),
    ("o que é empenho?", "class_buscar"),
    ("bom dia", "repasses_visao_geral"),
]


def validar_roteamento() -> list[str]:
    """Roda a tabela de ouro no roteador de fallback. Vazio = ok."""
    erros = []
    for pergunta, esperado in GOLDEN_ROTEAMENTO:
        obtido = agent.escolher_tool_fallback(pergunta)
        if obtido != esperado:
            erros.append(f"'{pergunta}' → {obtido} (esperado {esperado})")
    return erros
