"""Auditoria por IA — o registro coletado é mesmo uma proposta?

Segunda camada do gate de ingestão. A primeira (`ingestion/validador.py`) é
determinística e pega o resíduo ÓBVIO: identificador fabricado pela coleta,
registro sem nada que o identifique, página de erro no lugar do conteúdo. O que
ela não pega é o resíduo que se PARECE com dado: o parser de tabela que
desalinhou as colunas e gravou "R$ 10.000,00" como título; o cabeçalho da
página virado registro; o rodapé "Total geral" com valor somado. Isso tem
identificador, tem texto e tem valor — só não é uma proposta.

É aí que entra a LLM já configurada no painel (`llm_model_resumo`, o modelo
menor: isto é classificação, não redação). Ela recebe o registro normalizado e
responde se aquilo é um registro real de transferência/proposta do governo
federal ou resíduo da coleta.

DUAS TRAVAS, porque este é o único ponto do Hub em que a IA pode APAGAR dado:

1. `analisar` devolve None sempre que não tem certeza — IA desligada, chave
   inválida, rede fora, JSON torto, resposta fora do contrato. None significa
   "não sei", e quem chama MANTÉM o registro. Ausência de IA nunca vira
   exclusão.
2. O prompt manda aprovar na dúvida. Um falso negativo aqui esconde do gestor
   uma proposta que existe de verdade — dano pior que a linha suja.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from ..schemas.proposta import PropostaCanonica
from ..services import llm_providers
from ..services.municipios import rotulo

log = logging.getLogger("hubcapture.ai.validacao")

#: modelo default da auditoria — o mesmo tier do resumo (classificação barata)
_MODELO_DEFAULT = "claude-haiku-4-5-20251001"

_PROMPT = (
    "Você audita registros coletados dos portais de transferências do governo "
    "federal brasileiro (TransfereGov, Fundo Nacional de Saúde). Parte dos "
    "registros vem de raspagem de página e às vezes NÃO é uma transferência de "
    "verdade — é resíduo da coleta.\n\n"
    "É RESÍDUO quando o registro é, por exemplo:\n"
    "- linha de total/subtotal ou cabeçalho de tabela virada registro "
    '("Total geral", "Nº Transferência");\n'
    "- colunas desalinhadas pelo parser (o título é um valor em reais, uma "
    "data, um código solto ou uma situação);\n"
    "- texto de navegação, aviso de cookies, mensagem de erro ou de página "
    "sem resultado;\n"
    "- registro cujo conteúdo não descreve nenhum objeto, programa ou "
    "instrumento.\n\n"
    "É VÁLIDO quando descreve um programa, convênio, plano de ação, emenda ou "
    "objeto de transferência — MESMO que venha incompleto, com campos vazios, "
    "texto truncado, em CAIXA ALTA ou com nome pouco descritivo. Registro "
    "pobre não é registro inválido.\n\n"
    "Responda SOMENTE com um JSON no formato:\n"
    '{{"valido": true|false, "motivo": "<no máximo 12 palavras>"}}\n\n'
    "Na dúvida, responda true: descartar uma transferência real é pior que "
    "manter uma linha ruim.\n\n"
    "Registro:\n"
)


@dataclass(frozen=True)
class Veredito:
    """O que a IA concluiu. `valido=False` é o único caso que autoriza remoção."""

    valido: bool
    motivo: str


def _contexto(p: PropostaCanonica) -> str:
    """O registro como a IA o vê — os campos que distinguem dado de resíduo."""
    execucao = p.execucao or {}
    partes = [
        f"Município: {rotulo(p.municipio_nome, p.uf, p.municipio_ibge)}",
        f"Fonte: {p.fonte}",
        f"Identificador na fonte: {p.id_externo}",
        f"Nº da proposta: {p.numero_proposta or '—'}",
        f"Título: {p.titulo or '—'}",
        f"Objeto: {(p.objeto or '—')[:600]}",
        f"Órgão: {p.orgao_superior or '—'}",
        f"Modalidade: {p.modalidade or '—'}",
        f"Valor total: {p.valor_total if p.valor_total is not None else '—'}",
        f"Valor empenhado: {execucao.get('valor_empenhado') or '—'}",
        f"Situação: {p.situacao or '—'}",
    ]
    return "\n".join(partes)


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


async def analisar(proposta: PropostaCanonica) -> Veredito | None:
    """O registro é proposta de verdade? None = não deu para saber (mantenha).

    Nunca levanta: qualquer falha vira None, e quem chama preserva o registro.
    """
    params = await llm_providers.params_para("llm_model_resumo", _MODELO_DEFAULT)
    if params is None:  # IA desligada no painel — sem opinião, sem remoção
        return None
    try:
        import litellm  # import preguiçoso — só quando há chave

        resp = await litellm.acompletion(
            **params,
            messages=[{"role": "user", "content": _PROMPT + _contexto(proposta)}],
            max_tokens=200,
        )
        dados = _extrair_json(resp["choices"][0]["message"]["content"] or "")
    except Exception:
        log.warning("auditoria por IA falhou; registro mantido", exc_info=True)
        return None

    valido = dados.get("valido")
    if not isinstance(valido, bool):
        # fora do contrato: trata como "não sei" em vez de chutar uma remoção
        log.warning("auditoria por IA devolveu veredito fora do contrato: %r", dados)
        return None
    motivo = str(dados.get("motivo") or "").strip() or "sem motivo declarado"
    return Veredito(valido=valido, motivo=motivo[:200])
