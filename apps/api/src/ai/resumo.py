"""Resumo por IA (hook LiteLLM) — roda no pipeline de ingestão, não no clique.

Gera `resumo_ia` adaptado ao papel. Desabilitado sem `LLM_API_KEY` (retorna None),
para o Hub continuar entregando dados se o LLM cair. LiteLLM roteia o provider;
importado de forma preguiçosa para não virar dependência obrigatória.
"""

from __future__ import annotations

from ..schemas.proposta import PropostaCanonica
from ..services import llm_providers

_PROMPT = (
    "Resuma esta proposta de repasse do governo para um gestor público "
    "({papel}), em 1 parágrafo objetivo (valor, órgão, situação, prazo/pendência):\n"
)


def _contexto(p: PropostaCanonica) -> str:
    partes = [
        f"Título: {p.titulo}",
        f"Órgão: {p.orgao_superior}",
        f"Valor: {p.valor_total}",
        f"Situação: {p.situacao}",
        f"Município: {p.municipio_ibge}",
    ]
    return " · ".join(str(x) for x in partes)


async def gerar_resumo(proposta: PropostaCanonica, papel: str = "executivo") -> str | None:
    """Retorna o resumo, ou None se a IA está desabilitada (sem LLM API key)."""
    params = await llm_providers.params_para("llm_model_resumo", "claude-haiku-4-5-20251001")
    if params is None:
        return None
    try:
        import litellm  # import preguiçoso — só quando há chave
    except ImportError:
        return None
    resp = await litellm.acompletion(
        **params,
        messages=[{"role": "user", "content": _PROMPT.format(papel=papel) + _contexto(proposta)}],
        max_tokens=250,
    )
    return resp["choices"][0]["message"]["content"]
