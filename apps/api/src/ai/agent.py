"""Agente do Copiloto (Dynamic Island) — LLM com TOOL CALLING sobre o Hub.

O LLM não recebe um contexto pré-montado: ele DECIDE quais ferramentas chamar
e cada executor roda na MESMA sessão RLS do usuário — o agente só enxerga o
território do tenant, por construção. As ferramentas cobrem TODOS os eixos do
produto: captação (listar/detalhe/resumo/prazos/pareceres), MINHAS PROPOSTAS
(favoritas), repasses e emendas, conformidade, obras, alertas de atualização
(listar/varredura/marcar lidos), monitoramentos, pastas, contatos, municípios,
notícias, Class e pesquisa semântica. Há ferramentas de AÇÃO (favoritar
proposta, rodar varredura, marcar alertas lidos) — todas por-tenant e
reversíveis; nada de destrutivo vira ferramenta.

Degradação: sem nenhuma chave de LLM no painel, um roteador por palavra-chave
escolhe a ferramenta mais provável e devolve o dado formatado (o island
continua útil).

Streaming em DUAS fases (`preparar`): a fase 1 roda o loop de tools com a
sessão RLS do request viva e devolve os eventos {"tool": nome}; a fase 2 é um
gerador da resposta final que NÃO toca no banco — o router o consome depois
que a resposta HTTP já começou, então o texto pinta progressivamente no
island (resposta pronta sai fatiada; rodadas esgotadas fazem stream real).

Harness próprio (`Harness` + ai/harness.py): LLM, executores e catálogo de
tools são bordas injetáveis — o MESMO loop de produção roda nos testes e no
CLI (python -m src.tools.harness_copiloto) sem rede e sem banco.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.usuario import Usuario
from ..services import alertas as alertas_service
from ..services import conformidade as conformidade_service
from ..services import contatos as contatos_service
from ..services import criterios_alerta, llm_providers, rag
from ..services import favoritos as favoritos_service
from ..services import helpdesk as helpdesk_service
from ..services import modulos as modulos_service
from ..services import monitoramentos as monitoramentos_service
from ..services import municipios as municipios_service
from ..services import noticias as noticias_service
from ..services import obras as obras_service
from ..services import oportunidades as oportunidades_service
from ..services import pareceres as pareceres_service
from ..services import pastas as pastas_service
from ..services import perfil as perfil_service
from ..services import propostas as propostas_service
from ..services import repasses as repasses_service
from ..services._territorio import ibges as territorio_ibges

MAX_RODADAS = 6
# resposta já pronta é re-emitida em fatias deste tamanho (pintura progressiva)
_FATIA_STREAM = 48

SYSTEM = (
    "Você é o Copiloto do Hub Capture, no painel de um gestor público brasileiro "
    "({papel}). Você tem ferramentas que consultam os dados REAIS do território do "
    "usuário: propostas de captação (listar, detalhe, resumo financeiro, prazos, "
    "pareceres do plano de trabalho), as propostas FAVORITADAS em 'Minhas propostas', "
    "repasses recebidos e emendas parlamentares, conformidade fiscal, obras, alertas "
    "de ATUALIZAÇÃO de proposta (listar, rodar varredura, marcar lidos), "
    "monitoramentos, pastas, agenda de contatos, busca de municípios (IBGE), notícias "
    "oficiais, a central de aprendizagem Class e pesquisa semântica. Algumas "
    "ferramentas AGEM (favoritar proposta, varredura de alertas, marcar lidos) — use-as "
    "quando o usuário pedir a ação. Use as ferramentas antes de responder; responda em "
    "português, curto e direto, com valores em R$. Se a ferramenta voltar vazia, diga "
    "isso honestamente."
)


@dataclass
class Harness:
    """Harness próprio de tool calling: injeta as BORDAS do agente.

    `llm` substitui litellm.acompletion; `executor` substitui os executores
    reais (recebe (nome, args) e devolve o dict da ferramenta); `tools`
    substitui o catálogo ativo. Com as três injetadas, o loop de produção roda
    inteiro sem rede e sem banco (ver ai/harness.py)."""

    llm: Callable[..., Awaitable[Any]] | None = None
    executor: Callable[[str, dict], Awaitable[dict]] | None = None
    tools: dict[str, dict[str, Any]] | None = None


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _brl(v: Decimal | float | str | None) -> str:
    if v is None:
        return "—"
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _proposta_item(p) -> dict[str, Any]:
    """Resumo de UMA proposta na hierarquia da §35 (município → objeto → números)."""
    execucao = p.execucao or {}
    prazo = propostas_service.prazo_final_de(p)
    return {
        "municipio": p.municipio_nome or p.municipio_ibge,
        "titulo": p.titulo or p.objeto or "sem título na fonte",
        "numero_proposta": p.numero_proposta,
        "fonte": p.fonte,
        "valor_total": _num(p.valor_total),
        "empenhado": execucao.get("valor_empenhado"),
        "situacao": p.situacao,
        "tipo": propostas_service.classificar_tipo(p.situacao),
        "prazo_final": prazo.isoformat() if prazo else None,
    }


def _alerta_item(a) -> dict[str, Any]:
    payload = a.payload or {}
    return {
        "tipo": a.tipo,
        "lido": a.lido,
        "quando": a.created_at.isoformat() if a.created_at else None,
        "titulo": payload.get("titulo"),
        "municipio": payload.get("municipio_nome") or payload.get("municipio_ibge"),
        "detalhe": {k: v for k, v in payload.items() if k not in ("titulo",)},
    }


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
        q=args.get("busca"),
    )
    return {"total": len(rows), "propostas": [_proposta_item(p) for p in rows[:15]]}


async def _tool_minhas_propostas(session: AsyncSession, u: Usuario, _args: dict) -> dict[str, Any]:
    rows = await favoritos_service.listar_propostas(session, u.id)
    return {"total": len(rows), "propostas": [_proposta_item(p) for p in rows[:20]]}


async def _tool_proposta_detalhe(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    consulta = str(args.get("consulta") or "").strip()
    if not consulta:
        return {"erro": "informe o número ou um termo da proposta"}
    rows = await propostas_service.listar(session, q=consulta, municipio=args.get("municipio"))
    if not rows:
        return {"total": 0, "propostas": []}
    p = rows[0]
    execucao = p.execucao or {}
    return {
        "total": len(rows),
        "proposta": {
            **_proposta_item(p),
            "objeto": p.objeto,
            "orgao_superior": p.orgao_superior,
            "modalidade": p.modalidade,
            "contrapartida": _num(p.contrapartida),
            "prazos": p.prazos,
            "pendencias": p.pendencias,
            "movimentacao": p.movimentacao,
            "execucao": {
                k: execucao.get(k)
                for k in (
                    "valor_global",
                    "valor_empenhado",
                    "valor_liberado",
                    "valor_pago",
                    "saldo_conta",
                    "ano",
                )
                if execucao.get(k) is not None
            },
            "numero_plano_trabalho": p.numero_plano_trabalho,
            "url_origem": p.url_origem,
        },
        "outras": [_proposta_item(o) for o in rows[1:4]],
    }


async def _tool_captacao_resumo(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    r = await propostas_service.resumo(session, municipio=args.get("municipio"))
    return {
        "cards": {k: (_num(v) if isinstance(v, Decimal) else v) for k, v in r["cards"].items()},
        "pipeline": [
            {"situacao": i["situacao"], "quantidade": i["quantidade"], "valor": _num(i["valor"])}
            for i in r["pipeline"][:8]
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


async def _tool_pareceres(session: AsyncSession, u: Usuario, args: dict) -> dict[str, Any]:
    plano = str(args.get("plano") or "").strip()
    if not plano:
        return {"erro": "informe o número do plano de trabalho (ex.: 14275)"}
    itens, coleta = await pareceres_service.por_plano(session, plano, usuario_id=u.id)
    return {
        "status_coleta": coleta.status,
        "total": coleta.total,
        "pareceres": [
            {
                "data": i.data_parecer.isoformat() if i.data_parecer else None,
                "esfera": i.esfera,
                "situacao": i.situacao,
                "situacao_analise": i.situacao_analise,
                "responsavel": i.responsavel,
            }
            for i in itens[:10]
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


async def _tool_emendas(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    r = await repasses_service.resumo_emendas(
        session,
        municipio=args.get("municipio"),
        ano=args.get("ano"),
        parlamentar=args.get("parlamentar"),
    )
    return {
        "emendas": r.emendas,
        "empenhado": _num(r.empenhado),
        "pago": _num(r.pago),
        "percentual_executado": r.percentual_executado,
        "ranking_parlamentares": [
            {"parlamentar": x.parlamentar, "empenhado": _num(x.empenhado)}
            for x in r.ranking_parlamentares[:5]
        ],
    }


async def _tool_alertas(session: AsyncSession, u: Usuario, args: dict) -> dict[str, Any]:
    apenas_nao_lidos = bool(args.get("apenas_nao_lidos", True))
    rows = await alertas_service.listar(
        session, u.id, apenas_nao_lidos=apenas_nao_lidos, municipio=args.get("municipio")
    )
    return {
        "total": len(rows),
        "apenas_nao_lidos": apenas_nao_lidos,
        "alertas": [_alerta_item(a) for a in rows[:15]],
    }


async def _tool_varredura(session: AsyncSession, u: Usuario, _args: dict) -> dict[str, Any]:
    criados = await oportunidades_service.varredura(session, u)
    rows = await alertas_service.listar(session, u.id, apenas_nao_lidos=True)
    return {
        "alertas_criados": criados,
        "nao_lidos": len(rows),
        "alertas": [_alerta_item(a) for a in rows[:10]],
    }


async def _tool_marcar_lidos(session: AsyncSession, u: Usuario, _args: dict) -> dict[str, Any]:
    rows = await alertas_service.listar(session, u.id, apenas_nao_lidos=True)
    for a in rows:
        await alertas_service.marcar_lido(session, u.id, a.id)
    return {"marcados": len(rows)}


async def _tool_favoritar(session: AsyncSession, u: Usuario, args: dict) -> dict[str, Any]:
    consulta = str(args.get("consulta") or "").strip()
    if not consulta:
        return {"erro": "informe o número ou um termo que identifique a proposta"}
    rows = await propostas_service.listar(session, q=consulta)
    if not rows:
        return {"ok": False, "motivo": "nenhuma proposta encontrada com esse termo"}
    if len(rows) > 1:
        return {
            "ok": False,
            "motivo": "mais de uma proposta encontrada — peça para o usuário especificar",
            "candidatas": [_proposta_item(p) for p in rows[:5]],
        }
    p = rows[0]
    await favoritos_service.adicionar(session, u.id, p.id)
    return {"ok": True, "favoritada": _proposta_item(p)}


async def _tool_monitoramentos(session: AsyncSession, u: Usuario, _args: dict) -> dict[str, Any]:
    monitores = await monitoramentos_service.listar(session, u.id)
    buscas = await monitoramentos_service.listar_buscas(session, u.id)
    propostas = []
    for m in monitores[:10]:
        p = await propostas_service.obter(session, m.proposta_id)
        propostas.append(
            {
                "titulo": (p.titulo or p.objeto or p.id_externo) if p else str(m.proposta_id),
                "ativo": m.ativo,
                "canais": m.canais,
            }
        )
    return {
        "propostas_monitoradas": propostas,
        "buscas_de_futuras": [
            {
                "municipio_ibge": b.municipio_ibge,
                "area": b.area,
                "fonte": b.fonte,
                "ativo": b.ativo,
            }
            for b in buscas[:10]
        ],
    }


async def _tool_pastas(session: AsyncSession, u: Usuario, _args: dict) -> dict[str, Any]:
    pastas = await pastas_service.listar(session, u.id)
    itens = []
    for p in pastas[:20]:
        ids = await pastas_service.propostas_da_pasta(session, p.id)
        itens.append({"nome": p.nome, "propostas": len(ids)})
    return {"total": len(pastas), "pastas": itens}


async def _tool_contatos(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    rows = await contatos_service.listar(session, busca=args.get("busca") or None)
    return {
        "total": len(rows),
        "contatos": [
            {
                "nome": " ".join(x for x in (c.nome, c.sobrenome) if x),
                "organizacao": c.organizacao,
                "cargo": c.cargo,
                "emails": [e.get("valor") for e in (c.emails or []) if e.get("valor")],
                "telefones": [t.get("valor") for t in (c.telefones or []) if t.get("valor")],
            }
            for c in rows[:10]
        ],
    }


async def _tool_visao_geral(session: AsyncSession, u: Usuario, args: dict) -> dict[str, Any]:
    vg = await perfil_service.visao_geral(session, u, municipios_filtro=args.get("municipio"))
    return {
        "municipios": [f"{m.nome or m.ibge}{f'/{m.uf}' if m.uf else ''}" for m in vg.municipios],
        "dimensoes": [
            {"eixo": d.titulo, "total": d.total, "destaque": d.destaque} for d in vg.dimensoes
        ],
    }


async def _tool_municipios(_session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    achados = await municipios_service.buscar(str(args.get("nome") or ""))
    return {"municipios": achados}


async def _tool_class(session: AsyncSession, _u: Usuario, args: dict) -> dict[str, Any]:
    consulta = str(args.get("consulta") or "").strip()
    artigos = await helpdesk_service.listar_artigos(session, q=consulta or None)
    return {
        "artigos": [
            {"titulo": a.titulo, "resumo": a.resumo, "link": f"/panel/class/{a.slug}"}
            for a in artigos[:6]
        ]
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
            "fonte/situação/área/tipo (cadastrada|disponivel) e busca livre."
        ),
        "parametros": _p(
            dict(
                _MUN,
                fonte={"type": "string"},
                situacao={"type": "string"},
                area={"type": "string"},
                tipo={"type": "string", "enum": ["cadastrada", "disponivel"]},
                busca={"type": "string", "description": "busca livre (título/objeto/órgão)"},
            )
        ),
        "executor": _tool_propostas,
        "gatilhos": ("proposta", "captac", "edital", "convenio", "disponi", "cadastrad"),
        "modulo": "captacao",
    },
    "minhas_propostas": {
        "descricao": (
            "MINHAS PROPOSTAS: as propostas FAVORITADAS pelo usuário (aba "
            "Acompanhamento), com situação, valores e prazo de cada uma."
        ),
        "parametros": _p({}),
        "executor": _tool_minhas_propostas,
        "gatilhos": ("minhas proposta", "favorita", "salva", "acompanhamento", "estrela"),
        "modulo": "captacao",
    },
    "proposta_detalhe": {
        "descricao": (
            "Detalhe de UMA proposta (por número ou termo): objeto, órgão, valores, "
            "execução financeira (empenhado/pago), prazos, pendências e movimentação."
        ),
        "parametros": _p(
            dict(_MUN, consulta={"type": "string", "description": "nº da proposta ou termo"}),
            ["consulta"],
        ),
        "executor": _tool_proposta_detalhe,
        "gatilhos": ("detalhe", "andamento da", "como está a proposta", "situação da proposta"),
        "modulo": "captacao",
    },
    "captacao_resumo": {
        "descricao": (
            "Resumo FINANCEIRO da captação: valor conveniado, desembolsado, EMPENHADO, "
            "a utilizar, convênios em execução e pipeline por situação."
        ),
        "parametros": _p(dict(_MUN)),
        "executor": _tool_captacao_resumo,
        "gatilhos": ("empenh", "conveniad", "desembols", "pipeline", "resumo da capta"),
        "modulo": "captacao",
    },
    "propostas_prazos": {
        "descricao": "Propostas com PRAZO vencendo na janela de N dias ('o que vence este mês?').",
        "parametros": _p({"dias": {"type": "integer", "minimum": 1, "maximum": 365}}),
        "executor": _tool_prazos,
        "gatilhos": ("prazo", "venc", "expira", "data limite"),
        "modulo": "captacao",
    },
    "pareceres_plano": {
        "descricao": (
            "Pareceres do PLANO DE TRABALHO de uma proposta (veredito "
            "aprovar/reprovar/complementar, esfera e responsável), pelo nº do plano."
        ),
        "parametros": _p(
            {"plano": {"type": "string", "description": "nº do plano de trabalho"}}, ["plano"]
        ),
        "executor": _tool_pareceres,
        "gatilhos": ("parecer",),
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
    "emendas_resumo": {
        "descricao": (
            "Emendas parlamentares recebidas: empenhado/pago, % executado e "
            "ranking de parlamentares (filtros ano/parlamentar)."
        ),
        "parametros": _p(dict(_MUN, ano={"type": "string"}, parlamentar={"type": "string"})),
        "executor": _tool_emendas,
        "gatilhos": ("emenda", "parlamentar"),
        "modulo": "recebidos",
    },
    "alertas_atualizacoes": {
        "descricao": (
            "Alertas de ATUALIZAÇÃO das propostas do usuário (mudança de situação, "
            "prazo, pendência, nova proposta, oportunidade). Padrão: só não lidos."
        ),
        "parametros": _p(dict(_MUN, apenas_nao_lidos={"type": "boolean", "default": True})),
        "executor": _tool_alertas,
        "gatilhos": ("alerta", "atualiza", "mudou", "mudan", "não lido", "nao lido"),
    },
    "alertas_varredura": {
        "descricao": (
            "AÇÃO: roda a varredura de novidades AGORA (novas propostas das buscas "
            "monitoradas + oportunidades) e devolve os alertas gerados."
        ),
        "parametros": _p({}),
        "executor": _tool_varredura,
        "gatilhos": ("varredura", "varrer", "checar novidade", "procurar novidade"),
    },
    "alertas_marcar_lidos": {
        "descricao": "AÇÃO: marca TODOS os alertas não lidos do usuário como lidos.",
        "parametros": _p({}),
        "executor": _tool_marcar_lidos,
        "gatilhos": ("marcar lido", "marcar como lid", "limpar alerta"),
    },
    "favoritar_proposta": {
        "descricao": (
            "AÇÃO: favorita uma proposta (entra em 'Minhas propostas'). Identifique "
            "pelo nº ou termo; se ambíguo, devolve candidatas para o usuário escolher."
        ),
        "parametros": _p(
            {"consulta": {"type": "string", "description": "nº da proposta ou termo"}},
            ["consulta"],
        ),
        "executor": _tool_favoritar,
        "gatilhos": ("favoritar", "salvar a proposta", "salvar essa proposta", "acompanhar a "),
        "modulo": "captacao",
    },
    "monitoramentos_listar": {
        "descricao": (
            "O que o usuário MONITORA: propostas-chave acompanhadas e buscas de "
            "FUTURAS propostas (município/área/fonte) com canais de aviso."
        ),
        "parametros": _p({}),
        "executor": _tool_monitoramentos,
        "gatilhos": ("monitor",),
    },
    "pastas_listar": {
        "descricao": "Pastas de organização do usuário e quantas propostas há em cada uma.",
        "parametros": _p({}),
        "executor": _tool_pastas,
        "gatilhos": ("pasta",),
    },
    "contatos_buscar": {
        "descricao": (
            "Agenda de CONTATOS do usuário (gabinetes, secretarias, técnicos): "
            "busca por nome/organização/cargo, com e-mails e telefones."
        ),
        "parametros": _p({"busca": {"type": "string", "description": "nome/organização/cargo"}}),
        "executor": _tool_contatos,
        "gatilhos": ("contato", "telefone d", "e-mail d", "email d", "agenda"),
        "modulo": "contatos",
    },
    "perfil_visao_geral": {
        "descricao": (
            "Visão geral do território por eixo do ciclo (captação, recebidos, "
            "conformidade, obras) — o 'Meu painel' em números."
        ),
        "parametros": _p(dict(_MUN)),
        "executor": _tool_visao_geral,
        "gatilhos": ("visão geral", "visao geral", "panorama", "meu painel", "como estamos"),
    },
    "municipios_buscar": {
        "descricao": "Busca municípios por nome ou prefixo de código (IBGE Localidades).",
        "parametros": _p(
            {"nome": {"type": "string", "description": "nome do município ou código"}}, ["nome"]
        ),
        "executor": _tool_municipios,
        "gatilhos": ("ibge", "código do munic", "codigo do munic"),
    },
    "class_buscar": {
        "descricao": (
            "Central de aprendizagem Class (help desk): artigos e aulas que explicam "
            "termos e fluxos ('o que é empenho?', 'como cadastrar proposta?')."
        ),
        "parametros": _p({"consulta": {"type": "string", "description": "termo ou dúvida"}}),
        "executor": _tool_class,
        "gatilhos": ("o que é", "o que significa", "como funciona", "como faço", "aula", "aprend"),
        "modulo": "ajuda",
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
# (ex.: "quais propostas VENCEM" deve cair em prazos, não na listagem;
# "favoritar" deve cair na AÇÃO, não em minhas_propostas)
_PRIORIDADE_FALLBACK = (
    "alertas_marcar_lidos",
    "alertas_varredura",
    "favoritar_proposta",
    "minhas_propostas",
    "alertas_atualizacoes",
    "propostas_prazos",
    "pareceres_plano",
    "emendas_resumo",
    "monitoramentos_listar",
    "pastas_listar",
    "contatos_buscar",
    "municipios_buscar",
    "conformidade_resumo",
    "obras_resumo",
    # perguntas de VOCABULÁRIO ("o que é empenho?") vão ao Class antes do
    # resumo financeiro, que também gatilha em "empenh"
    "class_buscar",
    "captacao_resumo",
    "perfil_visao_geral",
    "noticias_transferegov",
    "proposta_detalhe",
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
    if "erro" in dado:
        return f"Não consegui consultar agora ({dado['erro']})."
    if nome == "repasses_visao_geral":
        fontes = ", ".join(f"{f['fonte']}: {_brl(f['total'])}" for f in dado.get("por_fonte", []))
        return (
            f"Seu território recebeu {_brl(dado.get('total_pago'))} em "
            f"{dado.get('movimentacoes', 0)} movimentações."
            + (f" Por fonte — {fontes}." if fontes else "")
        )
    if nome in ("propostas_listar", "minhas_propostas"):
        linhas = [
            f"• {p['titulo']} ({p['fonte']}, {p['situacao'] or 'sem situação'}, "
            f"{_brl(p['valor_total'])})"
            for p in dado.get("propostas", [])[:8]
        ]
        if nome == "minhas_propostas":
            return (
                f"Você acompanha {dado.get('total', 0)} proposta(s):\n" + "\n".join(linhas)
                if linhas
                else "Você ainda não favoritou nenhuma proposta — use a ★ em Propostas."
            )
        return (
            f"{dado.get('total', 0)} proposta(s) no seu território:\n" + "\n".join(linhas)
            if linhas
            else "Nenhuma proposta no cache do seu território ainda."
        )
    if nome == "proposta_detalhe":
        p = dado.get("proposta")
        if not p:
            return "Não encontrei nenhuma proposta com esse termo."
        partes = [
            f"{p['municipio']} — {p['titulo']}",
            f"Situação: {p['situacao'] or '—'} · Valor: {_brl(p['valor_total'])}",
        ]
        if p.get("empenhado") is not None:
            partes.append(f"Empenhado: {_brl(p['empenhado'])}")
        if p.get("prazo_final"):
            partes.append(f"Prazo final: {p['prazo_final']}")
        return "\n".join(partes)
    if nome == "captacao_resumo":
        c = dado.get("cards", {})
        return (
            f"Propostas: {c.get('transferencias', 0)} transferências — conveniado "
            f"{_brl(c.get('valor_conveniado'))}, empenhado {_brl(c.get('valor_empenhado'))}, "
            f"a utilizar {_brl(c.get('valor_a_utilizar'))}; "
            f"{c.get('oportunidades_abertas', 0)} oportunidade(s) aberta(s)."
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
    if nome == "pareceres_plano":
        linhas = [
            f"• {i.get('data') or '?'} — {i.get('esfera') or '?'}: "
            f"{i.get('situacao') or 'sem veredito'}"
            for i in dado.get("pareceres", [])
        ]
        return (
            "Pareceres do plano:\n" + "\n".join(linhas)
            if linhas
            else "Nenhum parecer encontrado para esse plano."
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
    if nome == "emendas_resumo":
        top = ", ".join(
            f"{x['parlamentar']}: {_brl(x['empenhado'])}"
            for x in dado.get("ranking_parlamentares", [])[:3]
        )
        return (
            f"Emendas: {dado.get('emendas', 0)} — empenhado {_brl(dado.get('empenhado'))}, "
            f"pago {_brl(dado.get('pago'))} "
            f"({dado.get('percentual_executado', 0):.0f}% executado)."
            + (f" Top parlamentares — {top}." if top else "")
        )
    if nome in ("alertas_atualizacoes", "alertas_varredura"):
        alertas = dado.get("alertas", [])
        linhas = [
            f"• [{criterios_alerta.rotulo(a.get('tipo'))}] "
            f"{a.get('titulo') or a.get('municipio') or ''}"
            for a in alertas[:8]
        ]
        cab = (
            f"Varredura feita: {dado.get('alertas_criados', 0)} alerta(s) novo(s), "
            f"{dado.get('nao_lidos', 0)} não lido(s)."
            if nome == "alertas_varredura"
            else f"{dado.get('total', 0)} alerta(s) de atualização."
        )
        return cab + ("\n" + "\n".join(linhas) if linhas else "")
    if nome == "alertas_marcar_lidos":
        return f"Pronto — {dado.get('marcados', 0)} alerta(s) marcados como lidos."
    if nome == "favoritar_proposta":
        if dado.get("ok"):
            fav = dado.get("favoritada", {})
            return f"Favoritei: {fav.get('titulo')} — está em Minhas propostas."
        return f"Não favoritei: {dado.get('motivo', 'não encontrei a proposta')}."
    if nome == "monitoramentos_listar":
        props = dado.get("propostas_monitoradas", [])
        buscas = dado.get("buscas_de_futuras", [])
        return (
            f"Você monitora {len(props)} proposta(s) e {len(buscas)} busca(s) de "
            "futuras propostas."
            + ("\n" + "\n".join(f"• {p['titulo']}" for p in props[:6]) if props else "")
        )
    if nome == "pastas_listar":
        linhas = [f"• {p['nome']} ({p['propostas']})" for p in dado.get("pastas", [])]
        return "Suas pastas:\n" + "\n".join(linhas) if linhas else "Você ainda não criou pastas."
    if nome == "contatos_buscar":
        linhas = [
            f"• {c['nome']}"
            + (f" — {c['organizacao']}" if c.get("organizacao") else "")
            + (f" · {c['telefones'][0]}" if c.get("telefones") else "")
            for c in dado.get("contatos", [])[:6]
        ]
        return "Contatos:\n" + "\n".join(linhas) if linhas else "Nenhum contato encontrado."
    if nome == "perfil_visao_geral":
        linhas = [
            f"• {d['eixo']}: {d['total']}" + (f" — {d['destaque']}" if d.get("destaque") else "")
            for d in dado.get("dimensoes", [])
        ]
        return "Seu território agora:\n" + "\n".join(linhas) if linhas else "Sem dados ainda."
    if nome == "municipios_buscar":
        linhas = [f"• {m['nome']}/{m['uf']} — IBGE {m['ibge']}" for m in dado.get("municipios", [])]
        return "Municípios:\n" + "\n".join(linhas) if linhas else "Nenhum município encontrado."
    if nome == "class_buscar":
        linhas = [f"• {a['titulo']} → {a['link']}" for a in dado.get("artigos", [])]
        return (
            "No Class:\n" + "\n".join(linhas)
            if linhas
            else "Não achei conteúdo no Class sobre isso."
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


async def _contexto_territorio(session: AsyncSession | None, territorio: Sequence[str]) -> str:
    """Frase de contexto com o recorte de município ativo no painel (ou vazia)."""
    if not territorio or session is None:
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
    tools: dict[str, dict[str, Any]] | None = None,
    harness: Harness | None = None,
) -> dict[str, Any]:
    catalogo = tools if tools is not None else TOOLS
    tool = catalogo.get(nome)
    if tool is None:
        return {"erro": f"ferramenta desconhecida: {nome}"}
    # O island flutua SOBRE o painel: se a tela está filtrada em alguns dos
    # municípios do perfil, a ferramenta consulta o mesmo recorte (o LLM só
    # sobrepõe isso se pedir um município explicitamente).
    if territorio and not args.get("municipio"):
        args = {**args, "municipio": list(territorio)}
    if harness is not None and harness.executor is not None:
        try:
            return await harness.executor(nome, args)
        except Exception as exc:  # noqa: BLE001 — mesma disciplina do executor real
            return {"erro": f"{type(exc).__name__}: falha ao consultar"}
    modulo = tool.get("modulo")
    if modulo is not None and not await modulos_service.esta_ativo(modulo):
        return {"erro": f"MODULO_DESATIVADO: {modulo}"}
    try:
        return await tool["executor"](session, usuario, args)
    except Exception as exc:  # ferramenta nunca derruba o agente
        return {"erro": f"{type(exc).__name__}: falha ao consultar"}


# ── fase 2: geradores da resposta final (NUNCA tocam no banco) ──────────────
def _fatiar(texto: str, tamanho: int = _FATIA_STREAM) -> list[str]:
    """Refatia uma resposta já pronta em pedaços por palavra — o front pinta
    progressivamente sem esperar o texto inteiro (concatenação == original)."""
    partes: list[str] = []
    atual = ""
    for palavra in texto.split(" "):
        atual = f"{atual} {palavra}" if atual else palavra
        if len(atual) >= tamanho:
            partes.append(atual)
            atual = ""
    if atual:
        partes.append(atual)
    return [p + " " if i < len(partes) - 1 else p for i, p in enumerate(partes)]


async def _gerar_texto_fatiado(texto: str) -> AsyncIterator[dict[str, Any]]:
    for fatia in _fatiar(texto):
        yield {"delta": fatia}


async def _gerar_stream_final(
    llm: Callable[..., Awaitable[Any]], params: dict | None, mensagens: list[dict]
) -> AsyncIterator[dict[str, Any]]:
    """Rodadas esgotadas: resposta final em streaming REAL (sem tools). Se o
    provider não streamar, cai para a chamada única."""
    emitiu = False
    try:
        stream = await llm(**(params or {}), messages=mensagens, stream=True)
        async for parte in stream:
            try:
                texto = (parte["choices"][0].get("delta") or {}).get("content")
            except (KeyError, IndexError, TypeError, AttributeError):
                texto = None
            if texto:
                emitiu = True
                yield {"delta": texto}
    except Exception:  # noqa: BLE001 — stream indisponível → chamada única abaixo
        pass
    if emitiu:
        return
    resp = await llm(**(params or {}), messages=mensagens)
    yield {"delta": resp["choices"][0]["message"].get("content") or ""}


async def preparar(
    session: AsyncSession,
    usuario: Usuario,
    pergunta: str,
    *,
    municipios: Sequence[str] | None = None,
    harness: Harness | None = None,
) -> tuple[list[dict[str, Any]], AsyncIterator[dict[str, Any]]]:
    """Fase 1 do agente: roda o loop de tools com a sessão RLS viva e devolve
    (eventos_de_tool, gerador_da_resposta_final). O gerador NÃO toca no banco —
    o router faz stream dele depois que a resposta HTTP já começou.

    `municipios` é o recorte de território ativo no painel; `harness` injeta
    LLM/executores/tools falsos (testes e CLI — ver ai/harness.py)."""
    territorio = territorio_ibges(municipios)
    h = harness or Harness()

    params: dict | None = None
    llm = h.llm
    if llm is None:
        params = await llm_providers.params_para("llm_model_chat", "claude-sonnet-5")
        if params is not None:
            try:
                import litellm

                llm = litellm.acompletion
            except ImportError:
                params = None

    tools = h.tools if h.tools is not None else await tools_ativas(session)
    if not tools:
        return [], _gerar_texto_fatiado(
            "Nenhum módulo de dados está ativo na plataforma no momento."
        )

    if llm is None:
        nome = escolher_tool_fallback(pergunta, tools)
        if nome is None:
            return [], _gerar_texto_fatiado(
                "Nenhum módulo de dados está ativo na plataforma no momento."
            )
        dado = await _executar_tool(
            session, usuario, nome, {}, territorio=territorio, tools=tools, harness=h
        )
        return [{"tool": nome}], _gerar_texto_fatiado(_formatar_fallback(nome, dado))

    hoje = date.today().isoformat()
    mensagens: list[dict] = [
        {
            "role": "system",
            "content": SYSTEM.format(papel=getattr(usuario, "papel", None) or "executivo")
            + f" Hoje é {hoje}."
            + await _contexto_territorio(session, territorio),
        },
        {"role": "user", "content": pergunta},
    ]
    eventos: list[dict[str, Any]] = []

    for _ in range(MAX_RODADAS):
        resp = await llm(**(params or {}), messages=mensagens, tools=_tools_openai(tools))
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return eventos, _gerar_texto_fatiado(msg.get("content") or "")
        mensagens.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )
        for tc in tool_calls:
            nome = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            eventos.append({"tool": nome})
            dado = await _executar_tool(
                session, usuario, nome, args, territorio=territorio, tools=tools, harness=h
            )
            mensagens.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(dado, ensure_ascii=False, default=str),
                }
            )

    # estourou as rodadas: resposta final SEM tools, em streaming real
    return eventos, _gerar_stream_final(llm, params, mensagens)


async def executar(
    session: AsyncSession,
    usuario: Usuario,
    pergunta: str,
    *,
    municipios: Sequence[str] | None = None,
    harness: Harness | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Loop do agente em UM iterador (compatibilidade com testes/chamadas
    diretas). Eventos: {'tool': nome} e {'delta': texto}."""
    eventos, final = await preparar(
        session, usuario, pergunta, municipios=municipios, harness=harness
    )
    for ev in eventos:
        yield ev
    async for ev in final:
        yield ev
