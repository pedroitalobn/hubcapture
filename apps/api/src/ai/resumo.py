"""Curadoria por IA (hook LiteLLM) — roda no pipeline de ingestão, não no clique.

Entrega duas coisas numa chamada só (metade do custo de duas): o `resumo_ia`
adaptado ao papel e as `categorias_ia` (as pílulas do painel), escolhidas dentro
da taxonomia fechada de `ai/categorias.py`.

Degrada com elegância, como o resto dos providers do Hub: sem credencial de LLM
no painel admin, `gerar_curadoria` devolve as categorias determinísticas (palavra
-chave) e resumo `None` — o painel continua com pílula, só não com resumo. Se a
IA responder algo fora do contrato, o mesmo caminho determinístico assume.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from ..schemas.proposta import PropostaCanonica
from ..services import llm_providers
from ..services.municipios import rotulo
from . import categorias as categorias_ai

log = logging.getLogger("hubcapture.ai.resumo")

_PROMPT = (
    "Você organiza repasses e propostas do governo federal para um gestor público "
    "({papel}) de município.\n\n"
    "Responda SOMENTE com um JSON no formato:\n"
    '{{"resumo": "<1 parágrafo objetivo>", "categorias": ["<slug>", ...]}}\n\n'
    "Regras:\n"
    "- resumo: 1 parágrafo (até 60 palavras) dizendo o que é, valor, órgão, "
    "situação e prazo/pendência quando houver. Cite o município pelo NOME, "
    "nunca pelo código IBGE. Português do Brasil, sem jargão "
    "e sem repetir o título em CAIXA ALTA.\n"
    "- categorias: de 1 a 3 slugs, APENAS desta lista: {taxonomia}.\n\n"
    "Proposta:\n"
)


@dataclass(frozen=True)
class Curadoria:
    """O que a curadoria produz. `resumo` é None quando a IA está desligada."""

    resumo: str | None
    categorias: list[str]


def _contexto(p: PropostaCanonica) -> str:
    # Município pelo NOME abre o contexto e o empenho entra junto do valor —
    # mesma hierarquia do header do detalhe (seção 23). Antes ia só o código
    # IBGE, e o resumo devolvia o número ao gestor.
    empenhado = (p.execucao or {}).get("valor_empenhado") if p.execucao else None
    partes = [
        f"Município: {rotulo(p.municipio_nome, p.uf, p.municipio_ibge)}",
        f"Título: {p.titulo}",
        f"Objeto: {(p.objeto or '')[:600]}",
        f"Órgão: {p.orgao_superior}",
        f"Modalidade: {p.modalidade}",
        f"Valor: {p.valor_total}",
        f"Empenhado: {empenhado or '—'}",
        f"Situação: {p.situacao}",
    ]
    return "\n".join(str(x) for x in partes)


def _categorias_locais(p: PropostaCanonica) -> list[str]:
    return categorias_ai.classificar(p.titulo, p.objeto, p.orgao_superior, p.modalidade)


def _extrair_json(bruto: str) -> dict:
    """Aceita a resposta pura ou embrulhada em cerca markdown (```json … ```)."""
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1] if "```" in texto[3:] else texto[3:]
        texto = texto.removeprefix("json").strip()
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise ValueError("resposta sem objeto JSON")
    return json.loads(texto[inicio : fim + 1])


async def gerar_curadoria(proposta: PropostaCanonica, papel: str = "executivo") -> Curadoria:
    """Resumo + categorias. Nunca levanta: cai no determinístico em qualquer falha."""
    locais = _categorias_locais(proposta)
    params = await llm_providers.params_para("llm_model_resumo", "claude-haiku-4-5-20251001")
    if params is None:  # IA desligada — pílula determinística já é entrega
        return Curadoria(resumo=None, categorias=locais)
    try:
        import litellm  # import preguiçoso — só quando há chave

        resp = await litellm.acompletion(
            **params,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(papel=papel, taxonomia=", ".join(categorias_ai.SLUGS))
                    + _contexto(proposta),
                }
            ],
            max_tokens=400,
        )
        dados = _extrair_json(resp["choices"][0]["message"]["content"] or "")
    except Exception:  # rede, chave inválida, JSON torto — o Hub segue entregando
        log.warning("curadoria por IA falhou; usando classificação local", exc_info=True)
        return Curadoria(resumo=None, categorias=locais)

    resumo = str(dados.get("resumo") or "").strip() or None
    escolhidas = categorias_ai.sanear(dados.get("categorias"))
    return Curadoria(resumo=resumo, categorias=escolhidas or locais)


async def gerar_resumo(proposta: PropostaCanonica, papel: str = "executivo") -> str | None:
    """Só o resumo (compat). None se a IA está desabilitada ou falhou."""
    return (await gerar_curadoria(proposta, papel)).resumo
