"""Resumo por IA (hook LiteLLM) — roda no pipeline de ingestão, não no clique.

Gera `resumo_ia` adaptado ao papel. Desabilitado sem `LLM_API_KEY` (retorna None),
para o Hub continuar entregando dados se o LLM cair. LiteLLM roteia o provider;
importado de forma preguiçosa para não virar dependência obrigatória.
"""

from __future__ import annotations

from ..core.config import settings
from ..schemas.proposta import PropostaCanonica

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
    """Retorna o resumo, ou None se a IA está desabilitada (sem LLM_API_KEY)."""
    if not settings.llm_api_key:
        return None
    try:
        import litellm  # import preguiçoso — só quando há chave
    except ImportError:
        return None
    resp = await litellm.acompletion(
        model=settings.llm_model_resumo,
        api_key=settings.llm_api_key,
        messages=[{"role": "user", "content": _PROMPT.format(papel=papel) + _contexto(proposta)}],
        max_tokens=250,
    )
    return resp["choices"][0]["message"]["content"]
