"""Agente do Copiloto (Dynamic Island) — LLM com TOOL CALLING sobre o Hub.

O LLM não recebe um contexto pré-montado: ele DECIDE quais ferramentas chamar
(repasses, propostas/fundos, prazos, conformidade, obras, notícias, pesquisa) e
cada executor roda na MESMA sessão RLS do usuário — o agente só enxerga o
território do tenant, por construção.

Degradação: sem nenhuma chave de LLM no painel, um roteador por palavra-chave
escolhe a ferramenta mais provável e devolve o dado formatado (o island continua
útil).

`executar()` produz eventos p/ SSE: {"tool": nome} a cada chamada de ferramenta
e {"delta": texto} com a resposta. O loop de tools roda ANTES do streaming da
resposta HTTP (a sessão do request precisa estar viva; ver api/v1/copiloto.py).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.usuario import Usuario
from ..services import conformidade as conformidade_service
from ..services import llm_providers, rag
from ..services import modulos as modulos_service
from ..services import noticias as noticias_service
from ..services import obras as obras_service
from ..services import perfil as perfil_service
from ..services import propostas as propostas_service
from ..services import repasses as repasses_service
from ..services._territorio import ibges as territorio_ibges

MAX_RODADAS = 4
SYSTEM = (
    "Você é o Copiloto do Hub Capture, no painel de um gestor público brasileiro "
    "({papel}). Você tem ferramentas que consultam os dados REAIS do território do "
    "usuário (repasses recebidos, propostas/fundos de captação, prazos, conformidade "
    "fiscal, obras, notícias oficiais). Use as ferramentas antes de responder; "
    "responda em português, curto e direto, com valores em R$. Se a ferramenta "
    "voltar vazia, diga isso honestamente."
)


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _brl(v: Decimal | float | None) -> str:
    if v is None:
        return "—"
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── executores (sessão RLS do usuário) ──────────────────────────────────────
async def _tool_repasses(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    vg = await repasses_service.visao_geral(session, municipio=args.get("municipio"))
    return {
        "total_pago": _num(vg.total_pago),
        "movimentacoes": vg.movimentacoes,
        "por_fonte": [
            {"fonte": f.fonte, "total": _num(f.total), "movimentacoes": f.movimentacoes}
            for f in vg.fontes
        ],
    }


async def _tool_propostas(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    rows = await propostas_service.listar(
        session,
        municipio=args.get("municipio"),
        fonte=args.get("fonte"),
        situacao=args.get("situacao"),
        area=args.get("area"),
        tipo=args.get("tipo"),
    )
    return {
        "total": len(rows),
        "propostas": [
            {
                "titulo": p.titulo or p.objeto or p.id_externo,
                "fonte": p.fonte,
                "municipio": p.municipio_nome or p.municipio_ibge,
                "valor_total": _num(p.valor_total),
                "situacao": p.situacao,
                "tipo": propostas_service.classificar_tipo(p.situacao),
            }
            for p in rows[:15]
        ],
    }


async def _tool_prazos(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    dias = int(args.get("dias") or 30)
    rows = await propostas_service.listar_por_prazo(
        session, dias=dias, municipio=args.get("municipio")
    )
    return {
        "janela_dias": dias,
        "vencendo": [
            {
                "titulo": p.titulo or p.objeto or p.id_externo,
                "fonte": p.fonte,
                "prazos": prazos,
            }
            for p, prazos in rows[:15]
        ],
    }


async def _tool_conformidade(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    r = await conformidade_service.resumo(session, municipio=args.get("municipio"))
    return {
        "total": r.total,
        "comprovados": r.comprovados,
        "a_comprovar": r.a_comprovar,
        "desativados": r.desativados,
        "capag": (
            (r.capag.status or (str(r.capag.valor) if r.capag.valor is not None else None))
            if r.capag
            else None
        ),
    }


async def _tool_obras(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    r = await obras_service.resumo(session, municipio=args.get("municipio"))
    return {
        "total": r.total,
        "em_execucao": r.em_execucao,
        "concluidas": r.concluidas,
        "paralisadas": r.paralisadas,
        "valor_investimento_total": _num(r.valor_investimento_total),
        "valor_repassado_total": _num(r.valor_repassado_total),
    }


async def _tool_noticias(_session: AsyncSession, _u: Usuario, _args: dict) -> dict[str, Any]:
    itens = await noticias_service.listar(limite=5)
    return {"noticias": [{"titulo": n.titulo, "url": n.url} for n in itens]}


async def _tool_pesquisar(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    rows = await rag.buscar_propostas(session, str(args.get("consulta") or ""))
    return {
        "resultados": [
            {
                "titulo": p.titulo or p.objeto or p.id_externo,
                "fonte": p.fonte,
                "situacao": p.situacao,
                "valor_total": _num(p.valor_total),
                "resumo": p.resumo_ia,
            }
            for p in rows
        ]
    }


def _p(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


_MUN = {"municipio": {"type": "string", "description": "código IBGE (7 dígitos), opcional"}}

TOOLS: dict[str, dict[str, Any]] = {
    "repasses_visao_geral": {
        "descricao": (
            "Total de recursos RECEBIDOS (repasses) pelo território, "
            "por fonte (FPM, FNS, FNDE, emendas…)."
        ),
        "parametros": _p(dict(_MUN)),
        "executor": _tool_repasses,
        "gatilhos": ("repasse", "receb", "fpm", "verba", "fundo", "transfer"),
        "modulo": "recebidos",
    },
    "propostas_listar": {
        "descricao": (
            "Propostas/fundos de CAPTAÇÃO do território, com filtros "
            "fonte/situação/área/tipo (cadastrada|disponivel)."
        ),
        "parametros": _p(
            dict(
                _MUN,
                fonte={"type": "string"},
                situacao={"type": "string"},
                area={"type": "string"},
                tipo={"type": "string", "enum": ["cadastrada", "disponivel"]},
            )
        ),
        "executor": _tool_propostas,
        "gatilhos": ("proposta", "captac", "edital", "convenio", "disponi", "cadastrad"),
        "modulo": "captacao",
    },
    "propostas_prazos": {
        "descricao": "Propostas com PRAZO vencendo na janela de N dias ('o que vence este mês?').",
        "parametros": _p({"dias": {"type": "integer", "minimum": 1, "maximum": 365}}),
        "executor": _tool_prazos,
        "gatilhos": ("prazo", "venc", "expira", "data limite"),
        "modulo": "captacao",
    },
    "conformidade_resumo": {
        "descricao": (
            "Conformidade fiscal do município (CAUC: itens comprovados/a comprovar; CAPAG)."
        ),
        "parametros": _p(dict(_MUN)),
        "executor": _tool_conformidade,
        "gatilhos": ("cauc", "capag", "conformidade", "fiscal", "certid"),
        "modulo": "conformidade",
    },
    "obras_resumo": {
        "descricao": (
            "Execução de OBRAS do município (em execução/concluídas/paralisadas e valores)."
        ),
        "parametros": _p(dict(_MUN)),
        "executor": _tool_obras,
        "gatilhos": ("obra", "execu", "sismob", "simec", "paralis"),
        "modulo": "obras",
    },
    "noticias_transferegov": {
        "descricao": "Últimas notícias oficiais do TransfereGov (editais, programas, avisos).",
        "parametros": _p({}),
        "executor": _tool_noticias,
        "gatilhos": ("notícia", "noticia", "novidade do governo", "comunicado"),
    },
    "pesquisar_propostas": {
        "descricao": "Pesquisa livre (semântica) nas propostas do território.",
        "parametros": _p(
            {"consulta": {"type": "string", "description": "termos de busca"}},
            ["consulta"],
        ),
        "executor": _tool_pesquisar,
        "gatilhos": ("pesquis", "procur", "busca", "encontr"),
        "modulo": "captacao",
    },
}


async def tools_ativas(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Só as ferramentas cujo módulo está ligado (painel admin). Um eixo
    desligado não pode ser respondido pelo copiloto — nem pelo LLM, nem pelo
    roteador de fallback."""
    ativos = await modulos_service.ativos(session)
    return {
        nome: t
        for nome, t in TOOLS.items()
        if t.get("modulo") is None or ativos.get(t["modulo"], False)
    }


def _tools_openai(tools: dict[str, dict[str, Any]]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": nome,
                "description": t["descricao"],
                "parameters": t["parametros"],
            },
        }
        for nome, t in tools.items()
    ]


# ordem de teste do roteador sem-LLM: gatilhos mais específicos primeiro
# (ex.: "quais propostas VENCEM" deve cair em prazos, não na listagem)
_PRIORIDADE_FALLBACK = (
    "propostas_prazos",
    "conformidade_resumo",
    "obras_resumo",
    "noticias_transferegov",
    "pesquisar_propostas",
    "propostas_listar",
    "repasses_visao_geral",
)


def escolher_tool_fallback(
    pergunta: str, tools: dict[str, dict[str, Any]] | None = None
) -> str | None:
    """Sem LLM: roteia por palavra-chave entre as ferramentas ATIVAS; padrão =
    visão de repasses (ou a primeira ativa, se recebidos estiver desligado).
    Devolve None quando nenhum módulo com ferramenta está ligado."""
    disponiveis = TOOLS if tools is None else tools
    baixa = pergunta.lower()
    for nome in _PRIORIDADE_FALLBACK:
        if nome in disponiveis and any(g in baixa for g in disponiveis[nome]["gatilhos"]):
            return nome
    if "repasses_visao_geral" in disponiveis:
        return "repasses_visao_geral"
    return next(iter(disponiveis), None)


def _formatar_fallback(nome: str, dado: dict[str, Any]) -> str:
    """Resposta legível sem LLM, direto do retorno da ferramenta."""
    if nome == "repasses_visao_geral":
        fontes = ", ".join(f"{f['fonte']}: {_brl(f['total'])}" for f in dado.get("por_fonte", []))
        return (
            f"Seu território recebeu {_brl(dado.get('total_pago'))} em "
            f"{dado.get('movimentacoes', 0)} movimentações."
            + (f" Por fonte — {fontes}." if fontes else "")
        )
    if nome == "propostas_listar":
        linhas = [
            f"• {p['titulo']} ({p['fonte']}, {p['situacao'] or 'sem situação'}, "
            f"{_brl(p['valor_total'])})"
            for p in dado.get("propostas", [])[:8]
        ]
        return (
            f"{dado.get('total', 0)} proposta(s) no seu território:\n" + "\n".join(linhas)
            if linhas
            else "Nenhuma proposta no cache do seu território ainda."
        )
    if nome == "propostas_prazos":
        linhas = [
            f"• {v['titulo']} ({v['fonte']}) → "
            + ", ".join(p.get("data_limite", "?") for p in v["prazos"])
            for v in dado.get("vencendo", [])[:8]
        ]
        return (
            f"Vencendo nos próximos {dado.get('janela_dias')} dias:\n" + "\n".join(linhas)
            if linhas
            else f"Nada vence nos próximos {dado.get('janela_dias')} dias."
        )
    if nome == "conformidade_resumo":
        return (
            f"Conformidade: {dado.get('comprovados', 0)} comprovados, "
            f"{dado.get('a_comprovar', 0)} a comprovar de {dado.get('total', 0)} itens."
            + (f" CAPAG: {dado['capag']}." if dado.get("capag") else "")
        )
    if nome == "obras_resumo":
        return (
            f"Obras: {dado.get('total', 0)} no total — {dado.get('em_execucao', 0)} em "
            f"execução, {dado.get('concluidas', 0)} concluídas, "
            f"{dado.get('paralisadas', 0)} paralisadas. Investimento "
            f"{_brl(dado.get('valor_investimento_total'))}."
        )
    if nome == "noticias_transferegov":
        linhas = [f"• {n['titulo']}" for n in dado.get("noticias", [])]
        return (
            "Últimas do TransfereGov:\n" + "\n".join(linhas)
            if linhas
            else ("Sem notícias disponíveis agora.")
        )
    if nome == "pesquisar_propostas":
        linhas = [
            f"• {r['titulo']} ({r['fonte']}, {_brl(r['valor_total'])})"
            for r in dado.get("resultados", [])
        ]
        return "Encontrei:\n" + "\n".join(linhas) if linhas else "Nada encontrado."
    return json.dumps(dado, ensure_ascii=False, default=str)


async def _contexto_territorio(session: AsyncSession, territorio: Sequence[str]) -> str:
    """Frase de contexto com o recorte de município ativo no painel (ou vazia)."""
    if not territorio:
        return ""
    municipios = await perfil_service.municipios_do_recorte(session, territorio)
    nomes = ", ".join(f"{m.nome or m.ibge}{f'/{m.uf}' if m.uf else ''}" for m in municipios)
    if not nomes:
        return ""
    return (
        f" O painel está filtrado no(s) município(s): {nomes} — responda sobre esse "
        "recorte, e diga qual é ele quando fizer diferença."
    )


async def _executar_tool(
    session: AsyncSession,
    usuario: Usuario,
    nome: str,
    args: dict,
    *,
    territorio: Sequence[str] | None = None,
) -> dict[str, Any]:
    tool = TOOLS.get(nome)
    if tool is None:
        return {"erro": f"ferramenta desconhecida: {nome}"}
    modulo = tool.get("modulo")
    if modulo is not None and not await modulos_service.esta_ativo(modulo):
        return {"erro": f"MODULO_DESATIVADO: {modulo}"}
    # O island flutua SOBRE o painel: se a tela está filtrada em alguns dos
    # municípios do perfil, a ferramenta consulta o mesmo recorte (o LLM só
    # sobrepõe isso se pedir um município explicitamente).
    if territorio and not args.get("municipio"):
        args = {**args, "municipio": list(territorio)}
    try:
        return await tool["executor"](session, usuario, args)
    except Exception as exc:  # ferramenta nunca derruba o agente
        return {"erro": f"{type(exc).__name__}: falha ao consultar"}


async def executar(
    session: AsyncSession,
    usuario: Usuario,
    pergunta: str,
    *,
    municipios: Sequence[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Loop do agente. Eventos: {'tool': nome} e {'delta': texto}.

    `municipios` é o recorte de território ativo no painel (quais dos
    municípios do perfil o usuário está vendo): entra como padrão das
    ferramentas e no contexto da conversa.
    """
    territorio = territorio_ibges(municipios)
    params = await llm_providers.params_para("llm_model_chat", "claude-sonnet-5")
    if params is not None:
        try:
            import litellm  # noqa: F401
        except ImportError:
            params = None

    tools = await tools_ativas(session)
    if not tools:
        yield {"delta": "Nenhum módulo de dados está ativo na plataforma no momento."}
        return

    if params is None:
        nome = escolher_tool_fallback(pergunta, tools)
        if nome is None:
            yield {"delta": "Nenhum módulo de dados está ativo na plataforma no momento."}
            return
        yield {"tool": nome}
        dado = await _executar_tool(session, usuario, nome, {}, territorio=territorio)
        yield {"delta": _formatar_fallback(nome, dado)}
        return

    import litellm

    hoje = date.today().isoformat()
    mensagens: list[dict] = [
        {
            "role": "system",
            "content": SYSTEM.format(papel=usuario.papel or "executivo")
            + f" Hoje é {hoje}."
            + await _contexto_territorio(session, territorio),
        },
        {"role": "user", "content": pergunta},
    ]

    for _ in range(MAX_RODADAS):
        resp = await litellm.acompletion(
            **params, messages=mensagens, tools=_tools_openai(tools)
        )
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            yield {"delta": msg.get("content") or ""}
            return
        mensagens.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )
        for tc in tool_calls:
            nome = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"tool": nome}
            dado = await _executar_tool(session, usuario, nome, args, territorio=territorio)
            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(dado, ensure_ascii=False, default=str),
                }
            )

    # estourou as rodadas: força resposta final sem tools
    resp = await litellm.acompletion(**params, messages=mensagens)
    yield {"delta": resp["choices"][0]["message"].get("content") or ""}
