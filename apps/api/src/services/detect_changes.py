"""Detecção de mudança da proposta monitorada — funções PURAS.

O `hash_conteudo` diz QUE algo mudou, nunca O QUE mudou — e era só isso que
existia aqui, então o alerta saía do mesmo jeito para qualquer alteração. Agora
a comparação é por CRITÉRIO (§51): `snapshot()` fotografa o estado material da
proposta (situação, publicação, empenho, pagamento, vigência, pareceres) e
`avaliar()` devolve uma mudança por critério LIGADO no monitoramento.

Sem banco e sem I/O de propósito: quem lê o cache é `services/oportunidades.py`,
que passa a proposta e as listas já carregadas. Assim o teste da regra roda sem
Postgres e a regra fica auditável.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .criterios_alerta import JANELA_VENCIMENTO_DIAS

# Campos do snapshot que cada critério observa. Campo fora desta tabela existe
# só para o payload (é o caso de `dias_para_vencer`, que muda TODO dia e, se
# comparado, geraria alerta diário sem nenhum fato novo).
CAMPOS_POR_CRITERIO: dict[str, tuple[str, ...]] = {
    "situacao": ("situacao", "movimentacao"),
    "prazo": ("prazos",),
    "pendencia": ("pendencias",),
    "publicacao": ("publicacao_situacao", "publicacao_valor"),
    "empenho": ("valor_empenhado", "empenhos_total", "empenhos_empenhado"),
    "pagamento": ("valor_pago", "valor_liberado", "empenhos_pago"),
    "parecer": ("pareceres_total", "pareceres_assinatura"),
    "vencimento": ("fim_vigencia", "vencimento_proximo"),
}

# rótulo humano de cada campo (entra na frase do alerta, do e-mail e do WhatsApp)
_ROTULO_CAMPO = {
    "situacao": "situação",
    "movimentacao": "movimentação",
    "prazos": "prazos",
    "pendencias": "pendências",
    "publicacao_situacao": "publicação",
    "publicacao_valor": "valor publicado",
    "valor_empenhado": "valor empenhado",
    "empenhos_total": "empenhos emitidos",
    "empenhos_empenhado": "valor empenhado (documentos)",
    "valor_pago": "valor pago",
    "valor_liberado": "valor liberado",
    "empenhos_pago": "valor pago (documentos)",
    "pareceres_total": "pareceres",
    "pareceres_assinatura": "parecer",
    "fim_vigencia": "fim de vigência",
}


@dataclass(frozen=True)
class Mudanca:
    criterio: str
    payload: dict[str, Any]


def _json(valor: Any) -> Any:
    """Serializa para caber no jsonb do snapshot (o alerta é auditoria)."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(k): _json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_json(v) for v in valor]
    return valor


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (ArithmeticError, ValueError):
        return None


def _soma(itens: list[Any], campo: str) -> Decimal:
    return sum((getattr(x, campo, None) or Decimal("0") for x in itens), Decimal("0"))


def _data(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return date.fromisoformat(valor.strip()[:10])
        except ValueError:
            return None
    return None


def _fim_vigencia(proposta: Any) -> date | None:
    """Vigência pela execução financeira e, sem ela, pelo prazo estruturado."""
    execucao = getattr(proposta, "execucao", None) or {}
    fim = _data(execucao.get("data_fim_vigencia"))
    if fim:
        return fim
    for prazo in getattr(proposta, "prazos", None) or []:
        if not isinstance(prazo, dict):
            continue
        if "vigência" in str(prazo.get("tipo") or "").lower():
            fim = _data(prazo.get("data_limite"))
            if fim:
                return fim
    return None


def _assinatura_parecer(p: Any) -> str:
    """Identidade material do parecer: muda quando o VEREDITO muda."""
    return "|".join(
        str(x or "")
        for x in (
            getattr(p, "id_externo", None),
            getattr(p, "situacao", None),
            getattr(p, "situacao_analise", None),
            getattr(p, "hash_conteudo", None),
        )
    )


def snapshot(
    proposta: Any,
    *,
    pareceres: list[Any] | None = None,
    empenhos: list[Any] | None = None,
    hoje: date | None = None,
) -> dict[str, Any]:
    """Fotografia comparável do estado da proposta (tudo JSON-serializável)."""
    hoje = hoje or date.today()
    execucao = getattr(proposta, "execucao", None) or {}
    pareceres = list(pareceres or [])
    empenhos = list(empenhos or [])

    fim = _fim_vigencia(proposta)
    dias = (fim - hoje).days if fim else None
    empenhado_docs = _soma(empenhos, "valor_empenhado") - _soma(empenhos, "valor_anulado")

    return {
        "situacao": proposta.situacao,
        "movimentacao": proposta.movimentacao,
        "prazos": _json(proposta.prazos),
        "pendencias": _json(proposta.pendencias),
        "publicacao_situacao": _json(execucao.get("situacao_publicacao")),
        "publicacao_valor": _json(_decimal(execucao.get("valor_publicado"))),
        "valor_empenhado": _json(_decimal(execucao.get("valor_empenhado"))),
        "valor_liberado": _json(_decimal(execucao.get("valor_liberado"))),
        "valor_pago": _json(_decimal(execucao.get("valor_pago"))),
        "empenhos_total": len(empenhos),
        "empenhos_empenhado": str(max(empenhado_docs, Decimal("0"))),
        "empenhos_pago": str(_soma(empenhos, "valor_pago")),
        "pareceres_total": len(pareceres),
        "pareceres_assinatura": sorted(_assinatura_parecer(p) for p in pareceres),
        "fim_vigencia": fim.isoformat() if fim else None,
        # entrou na janela de vencimento? é ISTO que dispara o aviso — não o
        # número de dias, que muda a cada varredura
        "vencimento_proximo": bool(fim and 0 <= (dias or 0) <= JANELA_VENCIMENTO_DIAS),
        "dias_para_vencer": dias,
        "capturado_em": datetime.now().astimezone().isoformat(),
    }


def _diff(antes: dict[str, Any], depois: dict[str, Any], campos: tuple[str, ...]) -> dict:
    return {
        campo: {"antes": antes.get(campo), "depois": depois.get(campo)}
        for campo in campos
        if antes.get(campo) != depois.get(campo)
    }


def _frase(criterio: str, diff: dict[str, Any], depois: dict[str, Any]) -> str:
    if criterio == "vencimento":
        dias = depois.get("dias_para_vencer")
        fim = depois.get("fim_vigencia")
        if "fim_vigencia" in diff:
            return f"Fim de vigência alterado para {fim or '—'}"
        if isinstance(dias, int):
            return f"Convênio vence em {dias} dia(s) ({fim})"
        return "Vigência do convênio atualizada"
    partes = []
    for campo, valores in diff.items():
        rotulo = _ROTULO_CAMPO.get(campo, campo)
        antes, atual = valores["antes"], valores["depois"]
        if isinstance(antes, list) or isinstance(atual, list) or antes in (None, ""):
            partes.append(f"{rotulo} atualizado(s)")
        else:
            partes.append(f"{rotulo}: {antes} → {atual}")
    return "; ".join(partes[:3]) or "Atualização na proposta"


def avaliar(
    antes: dict[str, Any] | None,
    depois: dict[str, Any],
    criterios: set[str],
) -> list[Mudanca]:
    """Uma mudança por critério LIGADO que teve fato novo desde `antes`.

    Sem linha de base (`antes` ausente, ou sem os campos do critério — caso de
    quem ligou o critério depois) nada é emitido: comparar contra o vazio
    marcaria a proposta inteira como "mudou" na primeira varredura. A exceção é
    `vencimento`, que é ESTADO e não diferença — convênio já dentro da janela
    precisa avisar hoje, não no próximo movimento da fonte.
    """
    mudancas: list[Mudanca] = []
    for criterio, campos in CAMPOS_POR_CRITERIO.items():
        if criterio not in criterios:
            continue
        sem_base = antes is None or any(campo not in antes for campo in campos)
        if sem_base:
            if criterio == "vencimento" and depois.get("vencimento_proximo"):
                mudancas.append(
                    Mudanca(
                        criterio,
                        {
                            "mudou": {},
                            "resumo": _frase(criterio, {}, depois),
                            "fim_vigencia": depois.get("fim_vigencia"),
                            "dias_para_vencer": depois.get("dias_para_vencer"),
                        },
                    )
                )
            continue

        diff = _diff(antes or {}, depois, campos)
        if not diff:
            continue
        if criterio == "vencimento":
            # sair da janela (venceu, ou a data foi empurrada) não é aviso de
            # vencimento; entrar nela e mudar a data são.
            entrou = depois.get("vencimento_proximo") and not (antes or {}).get(
                "vencimento_proximo"
            )
            if "fim_vigencia" not in diff and not entrou:
                continue
        payload: dict[str, Any] = {"mudou": diff, "resumo": _frase(criterio, diff, depois)}
        if criterio == "vencimento":
            payload["fim_vigencia"] = depois.get("fim_vigencia")
            payload["dias_para_vencer"] = depois.get("dias_para_vencer")
        mudancas.append(Mudanca(criterio, payload))
    return mudancas


def podar(snap: dict[str, Any], criterios: set[str]) -> dict[str, Any]:
    """Remove do snapshot os campos dos critérios DESLIGADOS.

    Guardar o campo de um critério que não foi coletado (pareceres/empenhos só
    são lidos quando o critério pede) gravaria um zero como se fosse o estado
    real: ao ligar o critério depois, a primeira varredura acusaria "3 pareceres
    novos" que já estavam lá. Sem o campo, `avaliar` trata como linha de base.
    """
    descartar = {
        campo
        for criterio, campos in CAMPOS_POR_CRITERIO.items()
        if criterio not in criterios
        for campo in campos
    }
    if "vencimento" not in criterios:
        descartar.add("dias_para_vencer")
    return {k: v for k, v in snap.items() if k not in descartar}
